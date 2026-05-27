# Plan: SCRUM-8 — FastAPI `/chat` Endpoint with Diagnostics

## Summary

Wrap the compiled LangGraph pipeline (`guardrails.pipeline.graph.build_graph`) behind a FastAPI service exposing `POST /chat` and `GET /health`. The graph and all heavy ML models (detoxify, DeBERTa, sentence-transformers loaded inside validators) are constructed once during a `lifespan` startup and stashed on `app.state`. `/chat` is a plain `def` handler so FastAPI auto-dispatches it on the Starlette threadpool — five concurrent requests run in parallel threads without blocking the event loop, and the sync `graph.invoke` (sync detoxify/DeBERTa/Anthropic SDK calls underneath) needs zero `await` plumbing. Each request gets a `request_id` (UUID4) bound through structlog context so log lines from the existing `log_blocked_event` / `log_passed_event` calls inside nodes correlate with the HTTP request. Response shape flattens the `GraphState` so `blocked`, `category`, and `diagnostics.{validator, rule_violated, latency_ms, retrieved_chunks}` all surface — Beat 4's `rule_violated="R2"` shows up via `block_details["rule_violated"]` which we expose under `diagnostics`. Block returns **HTTP 200** (policy decision, not error). RAG retrieve stays stubbed (mock chunks already shipped in nodes.py:28–32) — real Qdrant is SCRUM-9 territory.

## User Story

As a proxy corporativo, I want `POST /chat` accepting `session_id+message` and returning `response+blocked+category+diagnostics`, plus `GET /health` listing loaded validators, so that clients (Streamlit/curl) can drive the pipeline via HTTP.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | new `guardrails/api/` package; `pyproject.toml` (no new deps — FastAPI/uvicorn already declared) |
| Jira Issue | SCRUM-8 |
| Deadline | 2026-05-27 (MVP) |
| Branch | `feature/scrum-7-langgraph-pipeline` (continue here, or branch `feature/scrum-8-fastapi`) |

---

## Design Decisions (Locked)

| Decision | Why |
|----------|-----|
| `lifespan` builds graph + loads models eagerly; stashed on `app.state.graph` and `app.state.validators` | First request shouldn't pay ~10s cold-start; lifespan is the canonical FastAPI pattern; testable (TestClient triggers it). |
| `/chat` is **plain `def`** (not `async def`) | Pipeline is fully sync (detoxify, DeBERTa, Anthropic SDK, `graph.invoke`). `def` auto-runs in Starlette's 40-worker threadpool → 5 concurrent requests parallel for free. `async def` would block the loop. |
| Single uvicorn worker | Heavy models (~1.5GB) shouldn't be duplicated per worker. Threadpool handles concurrency within one process. |
| Block returns **HTTP 200** | Block is a successful policy decision, not a server error. Streamlit + curl both want a body either way. 4xx/5xx reserved for actual failures. |
| Response shape: flat top-level (`response, blocked, category`) + nested `diagnostics` | Matches AC literal wording. `block_details` exposed under `diagnostics.block_details` so `rule_violated` (Beat 4) and `entities` (PII demo) are visible for the demo client. |
| `request_id` UUID4 bound via structlog `contextvars.bind_contextvars` in middleware | The existing pipeline logger calls already emit JSON; binding `request_id` at the middleware layer adds it to every log line in that request without touching node code. |
| `/health` returns `validators_loaded` (names) + `models_loaded` (concrete model status booleans) | Honest about which validators actually load weights: detoxify + DeBERTa load real models; PII is regex; compliance is API client (no local weights). |
| Compliance fail-closed already implemented (compliance.py:121–135) | Timeout/API exception → `passed=False` → block. No additional API-layer error handling needed for that path. |
| Pydantic v2 models in `guardrails/api/schemas.py` | Project already uses pydantic 2.10+; matches existing `ValidatorResult` dataclass style. |
| **No new test infrastructure** — use `fastapi.testclient.TestClient` with mocked graph injected via `app.state` override | Mirrors `tests/unit/test_pipeline.py:36–62` mock-validator/mock-provider pattern. No real Anthropic/ML calls in CI. |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Lifespan triggers real model loads in tests, blowing up CI runtime | Tests override `app.state.graph` before first request, or use a fixture that bypasses the production lifespan and injects a mock graph. Add a TestClient fixture in `tests/api/conftest.py`. |
| Compliance API call inside `/chat` can take 1–3s, blocking thread | Threadpool absorbs this; 5 concurrent requests = 5 threads. AC requires 5 concurrent without 500s — comfortable. Document in plan: if N > 30, raise threadpool. |
| `block_details` may contain raw input spans (PII offsets) that leak structure | Demo only — span tuples are positions, not the PII itself. Logger already sanitizes via `sanitize_for_log`. For the API response, expose `block_details` as-is; if needed, redact `entities` keys later. Flag as Extra. |
| `state["message"]` is overwritten with FALLBACK on block; pipeline result no longer contains the original prompt | The API never echoes the user's prompt — only `response`. We pull `response = result["message"] if blocked else result["llm_response"]`. Original input was logged via `input_hash` at validator-time. |
| `setup_logging()` is global structlog config — calling it twice in tests | Guard with `cache_logger_on_first_use=True` (already set in logger.py:53). Lifespan calls `setup_logging()` once. |
| `get_config()` module-level singleton (`_config_cache`) may bleed between tests | Tests that need different configs reset it via `guardrails.config._config_cache = None` in a fixture. Document in conftest. |
| LangGraph compiled graph thread-safety | Per Context7 LangGraph docs: the compiled graph object is reusable across calls; per-request state lives in the `GraphState` dict. No checkpointer used here, so no shared mutable state. Safe. |

---

## Patterns to Follow

### Validator/Provider injection (build_graph factory)

```python
# SOURCE: guardrails/pipeline/graph.py:21-84
def build_graph(toxic=None, pii_input=None, ..., llm_provider=None, config=None):
    cfg = config or {}
    v_cfg = cfg.get("validators", {})
    if toxic is None:
        from guardrails.validators.toxic import ToxicValidator
        toxic = ToxicValidator(threshold=v_cfg.get("toxicity", {}).get("threshold", 0.7))
    # ... etc
```

→ **Apply**: The API lifespan calls `build_graph(config=get_config())` with zero validator overrides, letting the factory construct production instances.

### Mock-validator test pattern

```python
# SOURCE: tests/unit/test_pipeline.py:36-62
def _make_mock_validator(passed=True, category="toxicity", details=None):
    v = MagicMock()
    v.name = category
    v.run.return_value = ValidatorResult(passed=passed, category=category, ...)
    return v

def _build_all_pass_graph(llm_response="..."):
    return build_graph(
        toxic=_make_mock_validator(True, "toxicity"),
        pii_input=_make_mock_validator(True, "pii_input"),
        ...
        llm_provider=_make_mock_provider(llm_response),
    )
```

→ **Apply**: `tests/api/conftest.py` builds an all-pass graph and stuffs it onto `app.state.graph` before requests, bypassing real models.

### Diagnostics accumulation

```python
# SOURCE: guardrails/pipeline/nodes.py:80-88
return {
    "blocked": False,
    "diagnostics": {
        **state.get("diagnostics", {}),
        "input_guard_ms": (time.perf_counter() - t0) * 1000,
    },
}
```

→ **Apply**: API computes `total_ms = sum(diagnostics.values())` for the response — pure addition over pipeline-emitted per-stage floats.

### Logger init

```python
# SOURCE: guardrails/observability/logger.py:42-54
def setup_logging() -> None:
    import structlog
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
```

→ **Apply**: Lifespan calls `setup_logging()` once before serving. Middleware uses `structlog.contextvars.bind_contextvars(request_id=...)` per request.

### Pyproject project script (if we want `uvicorn` entrypoint)

```toml
# SOURCE: pyproject.toml (current state — no [project.scripts] yet)
[project]
name = "guardrail-safebank"
dependencies = ["fastapi>=0.115", "uvicorn[standard]>=0.34", ...]
```

→ **Apply**: Add a `[project.scripts]` entry `guardrails-api = "guardrails.api.app:run"` (optional, nice-to-have for `uv run guardrails-api`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/api/__init__.py` | CREATE | Package marker, re-export `app` and `create_app()` |
| `guardrails/api/schemas.py` | CREATE | Pydantic request/response models (`ChatRequest`, `ChatResponse`, `Diagnostics`, `HealthResponse`) |
| `guardrails/api/app.py` | CREATE | FastAPI app factory `create_app()`, lifespan with graph init, routes `/chat` + `/health`, request-id middleware, `run()` helper for uvicorn |
| `tests/api/__init__.py` | CREATE | Package marker |
| `tests/api/conftest.py` | CREATE | TestClient fixture with mocked graph injected into `app.state` |
| `tests/api/test_chat_endpoint.py` | CREATE | Tests covering all 5 AC items: benign, PII input, compliance R2 output, /health, concurrency |
| `tests/api/test_health_endpoint.py` | CREATE | Health endpoint validator/model loaded list |
| `README.md` | UPDATE | Add `## Running the API` section with `uvicorn guardrails.api.app:app` and curl examples |
| `CLAUDE.md` | UPDATE | Add row to Decisões table: "FastAPI `def` handler + lifespan + threadpool; block = HTTP 200" |
| `pyproject.toml` | UPDATE (optional) | Add `[project.scripts]` entry `guardrails-api` for convenience |

No new runtime dependencies. `fastapi`, `uvicorn[standard]`, `pydantic` already declared.

---

## Response Shape (Authoritative)

```python
# ChatRequest
{
  "message": str,                 # required, 1..4000 chars
  "session_id": str | None        # optional, used for log binding only (no session memory in MVP)
}

# ChatResponse (HTTP 200 for both pass and block)
{
  "response": str,                # llm_response on pass; FALLBACK_RESPONSE on block
  "blocked": bool,
  "category": str | None,         # "pii_input" | "pii_output" | "toxicity" | "jailbreak" | "compliance" | None
  "diagnostics": {
    "request_id": str,            # UUID4 echoed back for log correlation
    "validator": str | None,      # which validator fired (== category on block, None on pass)
    "rule_violated": str | None,  # "R1".."R5" if compliance fired, else None
    "severity": str | None,       # from SEVERITY_MAP on block
    "latency_ms": {
      "input_guard": float | None,
      "retrieve":    float | None,
      "generate":    float | None,
      "output_guard":float | None,
      "total":       float
    },
    "retrieved_chunks": list[str] | None,  # populated on pass; None on input-block (retrieve never ran)
    "block_details": dict | None           # raw block_details for demo visibility (entities, verdict, reasoning, ...)
  }
}

# HealthResponse
{
  "status": "ok",
  "validators_loaded": ["toxic", "pii_input", "pii_output", "jailbreak", "compliance"],
  "models_loaded": {
    "detoxify":       bool,  # toxic._model is not None
    "deberta":        bool,  # jailbreak._pipeline is not None
    "anthropic_judge": bool, # compliance.client is not None
    "anthropic_chat": bool   # llm_provider.client is not None
  }
}
```

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create Pydantic schemas

- **File**: `guardrails/api/schemas.py`
- **Action**: CREATE
- **Implement**:
  - `LatencyBreakdown` (BaseModel): four `float | None` fields + `total: float`
  - `Diagnostics` (BaseModel): `request_id: str`, `validator: str | None`, `rule_violated: str | None`, `severity: str | None`, `latency_ms: LatencyBreakdown`, `retrieved_chunks: list[str] | None`, `block_details: dict | None`
  - `ChatRequest` (BaseModel): `message: str = Field(min_length=1, max_length=4000)`, `session_id: str | None = None`
  - `ChatResponse` (BaseModel): `response: str`, `blocked: bool`, `category: str | None`, `diagnostics: Diagnostics`
  - `ModelsLoaded` (BaseModel): four `bool` fields
  - `HealthResponse` (BaseModel): `status: Literal["ok"]`, `validators_loaded: list[str]`, `models_loaded: ModelsLoaded`
- **Mirror**: `guardrails/pipeline/state.py` for naming style (snake_case, `from __future__ import annotations`)
- **Validate**: `uv run python -c "from guardrails.api.schemas import ChatRequest, ChatResponse; ChatRequest(message='hi')"`

### Task 2: Build FastAPI app with lifespan and routes

- **File**: `guardrails/api/app.py`
- **Action**: CREATE
- **Implement**:
  1. Imports: `FastAPI`, `Request`, `Response`, `contextlib.asynccontextmanager`, `uuid4`, `structlog`, schema models, `build_graph`, `get_config`, `setup_logging`.
  2. `@asynccontextmanager async def lifespan(app)`:
     - call `setup_logging()`
     - construct production validators and provider via `build_graph(config=get_config())` (the factory's defaults already do this)
     - stash on `app.state.graph`, plus references to underlying validators / provider for `/health` introspection: `app.state.toxic`, `app.state.jailbreak`, `app.state.compliance`, `app.state.llm`
     - `yield`
     - (no teardown needed; uvicorn shutdown handles process exit)
  3. `def create_app() -> FastAPI` returns `FastAPI(lifespan=lifespan, title="LLM Guardrails API")`. Builds-in:
     - middleware: assign `request_id = request.headers.get("x-request-id") or str(uuid4())`, bind via `structlog.contextvars.bind_contextvars(request_id=request_id)`, attach `request.state.request_id`, then `clear_contextvars()` after response.
     - `@app.post("/chat", response_model=ChatResponse) def chat(req: ChatRequest, request: Request):`
        - call `result = request.app.state.graph.invoke({"message": req.message, "diagnostics": {}})`
        - compute `blocked = result["blocked"]`
        - `response_text = result["message"] if blocked else result.get("llm_response", "")`
        - `category = result.get("block_category")`
        - `details = result.get("block_details") or {}`
        - build `LatencyBreakdown` from `result["diagnostics"]` keys + `total = sum(non-None values)`
        - `severity = SEVERITY_MAP.get(category) if category else None`
        - `validator = category` (the firing validator name maps 1:1 to category)
        - `rule_violated = details.get("rule_violated")`
        - `retrieved_chunks = result.get("retrieved_chunks") if not blocked else None`
        - return `ChatResponse(response=..., blocked=..., category=..., diagnostics=Diagnostics(...))`
     - `@app.get("/health", response_model=HealthResponse) def health(request: Request):`
        - inspect `app.state.toxic._model`, `app.state.jailbreak._pipeline`, `app.state.compliance.client`, `app.state.llm.client` (attribute names confirmed in validators)
        - validators_loaded list = `["toxic", "pii_input", "pii_output", "jailbreak", "compliance"]` (static — these are always built)
  4. Module-level `app = create_app()` so `uvicorn guardrails.api.app:app` works.
  5. `def run() -> None`: `uvicorn.run("guardrails.api.app:app", host="0.0.0.0", port=8000, workers=1)` — convenience entrypoint.
- **Mirror**: `guardrails/pipeline/graph.py:21–84` for the DI/factory style; `guardrails/observability/logger.py:42–54` for structlog setup placement.
- **Validate**:
  - `uv run python -c "from guardrails.api.app import create_app; create_app()"` (lifespan not triggered, just construction)
  - `uv run ruff check guardrails/api/`

### Task 3: Add `__init__.py` for the api package

- **File**: `guardrails/api/__init__.py`
- **Action**: CREATE
- **Implement**: `from guardrails.api.app import app, create_app  # noqa: F401`
- **Validate**: `uv run python -c "from guardrails.api import app"`

### Task 4: TestClient fixture with mocked graph

- **File**: `tests/api/__init__.py` (empty) + `tests/api/conftest.py`
- **Action**: CREATE
- **Implement** in `conftest.py`:
  - import `pytest`, `TestClient`, `MagicMock`, `ValidatorResult`, `create_app`, `build_graph`, plus the mock-validator helpers from `tests/unit/test_pipeline.py` (extract them into `tests/_fakes.py` OR copy locally — copy is faster given deadline).
  - fixture `mock_graph_factory(monkeypatch)` that patches `guardrails.api.app.build_graph` to return a graph built with mock validators (parametrized by which validators should pass/fail and what `block_details` they return).
  - fixture `client(mock_graph_factory)` that yields `TestClient(create_app())` so lifespan runs (uses the mocked `build_graph`, never touches real models).
  - reset `guardrails.config._config_cache = None` between tests.
- **Mirror**: `tests/unit/test_pipeline.py:36–62` for the mock validator/provider helpers.
- **Validate**: `uv run pytest tests/api/ --collect-only`

### Task 5: `/chat` endpoint tests (AC items 1, 2, 3)

- **File**: `tests/api/test_chat_endpoint.py`
- **Action**: CREATE
- **Implement** (one test per AC):
  1. `test_chat_benign_returns_response_and_diagnostics`: all validators pass, llm returns "Olá". Assert 200, `blocked is False`, `category is None`, `diagnostics.retrieved_chunks` non-empty, all four `latency_ms.*` floats present, `latency_ms.total > 0`.
  2. `test_chat_pii_input_blocked`: pii_input validator fails with `{"entities": {"cpf": [(0, 14)]}}`. Assert 200, `blocked is True`, `category == "pii_input"`, `diagnostics.validator == "pii_input"`, `diagnostics.block_details["entities"]` present.
  3. `test_chat_compliance_r2_blocked`: compliance validator fails with `{"verdict": "fail", "rule_violated": "R2", "reasoning": "..."}`, output guard blocks. Assert 200, `blocked is True`, `category == "compliance"`, `diagnostics.rule_violated == "R2"`.
  4. `test_chat_returns_request_id`: assert `diagnostics.request_id` is a valid UUID hex; if client sends `X-Request-ID` header, that value is echoed.
  5. `test_chat_validates_empty_message`: empty `message` → 422 (pydantic validation).
- **Mirror**: `tests/unit/test_pipeline.py:100–182` test naming & assertion style.
- **Validate**: `uv run pytest tests/api/test_chat_endpoint.py -v`

### Task 6: `/health` endpoint tests (AC item 4)

- **File**: `tests/api/test_health_endpoint.py`
- **Action**: CREATE
- **Implement**:
  1. `test_health_returns_validators_loaded`: GET `/health` → 200, body contains `validators_loaded` list of 5 names, `models_loaded` dict with 4 bool fields, `status == "ok"`.
  2. `test_health_models_loaded_reflects_state`: with mocked validators where `_model` attrs are `None`/`MagicMock`, assert booleans flip correctly.
- **Validate**: `uv run pytest tests/api/test_health_endpoint.py -v`

### Task 7: Concurrency test (AC item 5)

- **File**: append to `tests/api/test_chat_endpoint.py`
- **Action**: UPDATE
- **Implement**: `test_chat_handles_5_concurrent_requests`: use `concurrent.futures.ThreadPoolExecutor(max_workers=5)` to fire 5 simultaneous `client.post("/chat", ...)`. Assert all return 200, no exceptions. (TestClient is thread-safe for parallel calls in modern Starlette.)
- **Validate**: `uv run pytest tests/api/test_chat_endpoint.py::test_chat_handles_5_concurrent_requests -v`

### Task 8: Manual smoke (no automation, document only)

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: add `## Running the API` section with:
  ```bash
  uv run uvicorn guardrails.api.app:app --reload
  curl -X POST http://localhost:8000/chat -H 'content-type: application/json' \
       -d '{"message": "Como funciona o cartão Gold?"}' | jq
  curl -X POST http://localhost:8000/chat -H 'content-type: application/json' \
       -d '{"message": "Meu CPF é 123.456.789-09"}' | jq
  curl http://localhost:8000/health | jq
  ```
  Plus note about `ANTHROPIC_API_KEY` env var.
- **Validate**: human read-through

### Task 9: Update CLAUDE.md decisions table

- **File**: `CLAUDE.md`
- **Action**: UPDATE
- **Implement**: append row to the Decisões table:
  > **API: FastAPI `def` handlers + lifespan + Starlette threadpool**; block = HTTP 200 (policy decision, not error); single uvicorn worker (models ~1.5GB shouldn't duplicate); `request_id` UUID4 via structlog `contextvars`. | Definido (2026-05-26)
- **Validate**: human read-through

### Task 10: Optional — uv script entrypoint

- **File**: `pyproject.toml`
- **Action**: UPDATE
- **Implement**: add `[project.scripts]` table with `guardrails-api = "guardrails.api.app:run"`
- **Validate**: `uv pip install -e . && uv run guardrails-api` boots the server. (Skip if time-tight.)

### Task 11: Adversarial / building-rigorously gate

- **File**: notes only (not code)
- **Action**: review per `building-rigorously.md` §2
- **Implement**:
  - Confirm tests cover the 3 demo Beats (PII CPF, jailbreak DAN, compliance R2) end-to-end through the HTTP layer, not just via mocks. (Mocks are OK for CI, but at least one manual curl per Beat against the live stack before declaring done.)
  - Verify compliance fail-closed actually surfaces as a block via HTTP — simulate by raising in the mock validator, assert `blocked is True`.
  - Confirm AC item 5 isn't tautological: 5 concurrent should hit the **real** graph in a separate run (not all-mock) to validate the threadpool path. Document this as a manual smoke step.
- **Validate**: subjective; record findings in PR description.

---

## Validation

```bash
# Lint
uv run ruff check guardrails/api tests/api

# Unit tests (mocked, fast)
uv run pytest tests/api -v

# Whole-suite regression
uv run pytest -v

# Manual smoke (requires ANTHROPIC_API_KEY)
uv run uvicorn guardrails.api.app:app &
curl -X POST localhost:8000/chat -H 'content-type: application/json' -d '{"message":"Como funciona o cartão Gold?"}' | jq
curl -X POST localhost:8000/chat -H 'content-type: application/json' -d '{"message":"Meu CPF é 123.456.789-09"}' | jq
curl localhost:8000/health | jq

# Concurrency smoke
seq 5 | xargs -P5 -I{} curl -s -X POST localhost:8000/chat -H 'content-type: application/json' -d '{"message":"oi"}' > /dev/null && echo OK
```

---

## Acceptance Criteria Mapping (Jira)

| AC item | Covered by |
|---|---|
| `POST /chat` benign → 200 with response + diagnostics + retrieved_chunks | Task 5 test #1 |
| `POST /chat` PII input → 200, `blocked=true`, `category="pii_input"`, `diagnostics.validator="pii_input"` | Task 5 test #2 |
| Beat 4 compliance R2 → 200, `blocked=true`, `category="compliance"`, `diagnostics.rule_violated="R2"` | Task 5 test #3 |
| `GET /health` returns `validators_loaded` + `models_loaded` | Task 6 |
| 5 concurrent requests no 500s | Task 7 + manual smoke |

---

## Out of Scope (Defer to Next Stories / Extras)

- Real Qdrant retrieval (SCRUM-9 owns this; the mock chunks satisfy `retrieved_chunks` for the demo).
- Streaming responses (Extras).
- Session memory / checkpointer (would need `{"configurable": {"thread_id": session_id}}` + `SqliteSaver`; Extras).
- Rate limiting / auth (proxy is for the interview demo; not in scope).
- PII masking in `block_details.entities` for non-debug clients (Extras).
- OpenAPI tags / docs prettification — FastAPI auto-generates `/docs`; sufficient for demo.

---

## Estimated Time

| Task | Estimate |
|---|---|
| 1 (schemas) | 15 min |
| 2 (app + routes + lifespan) | 60 min |
| 3 (init) | 2 min |
| 4 (conftest) | 30 min |
| 5 (chat tests) | 45 min |
| 6 (health tests) | 20 min |
| 7 (concurrency test) | 15 min |
| 8 (README) | 10 min |
| 9 (CLAUDE.md) | 5 min |
| 10 (optional script) | 5 min |
| 11 (adversarial gate) | 30 min |
| **Total** | **~3.5–4 h** |

Comfortably fits inside the remaining day before the 2026-05-27 MVP deadline.
