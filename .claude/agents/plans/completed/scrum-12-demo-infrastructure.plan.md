# Plan: SCRUM-12 — Demo Infrastructure (Streamlit + Docker + CI)

## Summary

Deliver the visual and infrastructure layer that makes the guardrail demo runnable with a single command. This plan covers four self-contained workstreams: (1) commit the critical system-prompt fix already in the working tree, (2) build the Streamlit chat client with color-coded diagnostics, (3) create Docker infrastructure for one-command demo startup, and (4) add a CI pipeline (GitHub Actions). Together these close the gap between a curl-able API and a showcase-ready demo.

## User Story

As a demo evaluator,
I want to run `docker compose up` and interact with a visual chat UI
So that the 4 demo beats (happy path, jailbreak, PII, compliance R2) are immediately accessible, visually impactful, and self-explanatory

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `ui/` (new) · `docker/` (new) · `.github/workflows/` (new) · `guardrails/adapters/llm.py` · `guardrails/pipeline/nodes.py` · `pyproject.toml` · `.gitignore` · `README.md` |
| Jira Issue | SCRUM-12 |

## Key Decisions (Locked)

1. **Streamlit**: single file (`ui/streamlit_app.py`), no multi-page, no routing. All UI text in PT-BR.
2. **API URL**: configurable via `API_URL` env var (default `http://localhost:8000`). No config.yaml dependency.
3. **HTTP client**: `httpx` (already in project deps) instead of `requests` — avoids adding a new dependency.
4. **Docker**: multi-stage `Dockerfile.api` for the FastAPI service (pre-downloads HF models in build stage); slim `Dockerfile.ui` for Streamlit. `docker-compose.yml` wires 4 services: `api`, `ui`, `qdrant`, `ingest` (one-shot).
5. **CI**: single GitHub Actions workflow with matrix steps (lint → test → adversarial smoke → docker build). No deployment step (local-only MVP).
6. **System prompt fix**: commit the already-coded changes in `llm.py` and `nodes.py` (they add `system` param support and fix the dead-code bug where the chatbot persona was never sent).
7. **README**: update Quick Start to reflect `docker compose up`.

---

## Patterns to Follow

### FastAPI app factory pattern
```
// SOURCE: guardrails/api/app.py:24-91
def _create_components(cfg):
    """Construct all validators, LLM provider, RAG adapters, and compiled graph.
    Separated from the lifespan so tests can patch this single call."""
    ...

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    graph, ... = _create_components(get_config())
    app.state.graph = graph
    yield
```

### API response schema for Streamlit consumption
```
// SOURCE: guardrails/api/schemas.py:31-35
class ChatResponse(BaseModel):
    response: str
    blocked: bool
    category: str | None
    diagnostics: Diagnostics
```

### Diagnostics shape for UI rendering
```
// SOURCE: guardrails/api/schemas.py:8-23
class LatencyBreakdown(BaseModel):
    input_guard: float | None
    retrieve: float | None
    generate: float | None
    output_guard: float | None
    total: float

class Diagnostics(BaseModel):
    request_id: str
    validator: str | None
    rule_violated: str | None
    severity: str | None
    latency_ms: LatencyBreakdown
    retrieved_chunks: list[str] | None
    block_details: dict[str, Any] | None
```

### Category constants for badge coloring
```
// SOURCE: guardrails/pipeline/state.py:16-20
CATEGORY_TOXICITY = "toxicity"
CATEGORY_PII_INPUT = "pii_input"
CATEGORY_PII_OUTPUT = "pii_output"
CATEGORY_JAILBREAK = "jailbreak"
CATEGORY_COMPLIANCE = "compliance"
```

### Fallback response text for blocked messages
```
// SOURCE: guardrails/pipeline/nodes.py:26
FALLBACK_RESPONSE = "Sua mensagem não pôde ser processada porque viola nossas políticas de segurança. Por favor, reformule sua pergunta."
```

### Script entry point pattern
```
// SOURCE: scripts/ingest_banking_kb.py:137-138
if __name__ == "__main__":
    raise SystemExit(main())
```

### Test helper factories (mocking HTTP)
```
// SOURCE: tests/api/conftest.py:44-52
def _make_mock_validator(passed=True, category="toxicity", details=None) -> MagicMock:
    v = MagicMock()
    v.name = category
    v.run.return_value = _passing_result(category) if passed else _failing_result(category, details)
    return v
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/adapters/llm.py` | UPDATE | Add `system` param to `LLMProvider` protocol + `AnthropicProvider` (already coded, needs staging) |
| `guardrails/pipeline/nodes.py` | UPDATE | Pass `CHATBOT_SYSTEM_PROMPT` via `system=` kwarg (already coded, needs staging) |
| `ui/__init__.py` | CREATE | Package marker |
| `ui/streamlit_app.py` | CREATE | Main chat UI with diagnostics display |
| `pyproject.toml` | UPDATE | Add streamlit scripts entry point |
| `.gitignore` | UPDATE | Ignore `.streamlit/` config dir |
| `docker/Dockerfile.api` | CREATE | Multi-stage Dockerfile for FastAPI service |
| `docker/Dockerfile.ui` | CREATE | Slim Dockerfile for Streamlit service |
| `docker-compose.yml` | CREATE | 4-service orchestration (api, ui, qdrant, ingest) |
| `.github/workflows/ci.yml` | CREATE | Lint + test + adversarial smoke + docker build |
| `README.md` | UPDATE | Refresh Quick Start to `docker compose up` |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Commit system-prompt fix

- **Files**:
  - `guardrails/adapters/llm.py` — UPDATE
  - `guardrails/pipeline/nodes.py` — UPDATE
- **Action**: STAGE + COMMIT
- **Implement**: The changes are already in the working tree (unstaged). `llm.py` adds `system: str | None = None` to both the `LLMProvider` protocol and `AnthropicProvider.complete()` / `complete_with_tools()`, passing it through to the Anthropic API with `cache_control`. `nodes.py` drops the dead `system_msg` variable and passes `system=CHATBOT_SYSTEM_PROMPT` to `llm.complete()`. Stage both files and commit with message `fix(SCRUM-12): pass chatbot system prompt to LLM provider`.
- **Validate**: `git diff --cached` shows only these two files; `uv run pytest -m "not slow and not network" -q` still passes

### Task 1: Create Streamlit client

- **File**: `ui/__init__.py` — CREATE (empty)
- **File**: `ui/streamlit_app.py` — CREATE
- **Action**: CREATE
- **Implement**:
  1. `from __future__ import annotations`. Use `httpx` (already in deps) to POST to `{API_URL}/chat` where `API_URL` comes from `os.environ.get("API_URL", "http://localhost:8000")`.
  2. Full-width layout via `st.set_page_config(layout="wide")`. Title "Banco Seguro — Assistente Virtual", subtitle "Guardrail Bancário · Demo".
  3. Initialize `st.session_state` keys: `messages: list[dict]` (each has `role`, `content`, `blocked`, `category`, `diagnostics`), `show_diagnostics: bool` (from sidebar toggle).
  4. Chat history render loop: iterate `st.session_state.messages`, for each turn:
     - **User message**: plain styling via `st.chat_message("user")`.
     - **Assistant message**: via `st.chat_message("assistant")`. Color-coded badge prepended:
       - `blocked=False` → green `✅ OK` label + response text
       - `blocked=True` → red `🚫 BLOQUEADO [{category}]` label + `rule_violated` if present + fallback text
     - Below each assistant message (when `show_diagnostics` is on or always for blocked), a `st.expander("Diagnósticos")` showing:
       - Latency breakdown table (input_guard, retrieve, generate, output_guard, total in ms)
       - Category, severity, rule_violated
       - `block_details` as formatted JSON (`st.json`)
       - `retrieved_chunks` as bullet list (if present)
  5. Chat input at bottom via `st.chat_input("Digite sua mensagem...")`. On submit:
     - Append `{"role": "user", "content": text}` to history
     - POST to `{api_url}/chat` with `{"message": text}`
     - Parse response JSON into `ChatResponse` shape
     - Append assistant entry with all diagnostics fields
     - On network error (`httpx.HTTPError`, `ConnectionError`): append `{"role": "assistant", "content": "Serviço indisponível. Tente novamente mais tarde.", "blocked": True, "category": "error"}` without crashing
  6. Sidebar via `st.sidebar`:
     - Toggle "Exibir modo diagnóstico" (checkbox, defaults to True) — controls whether expanders are open by default
     - Button "Limpar conversa" (resets `st.session_state.messages`)
     - Health check indicator: `st.caption(f"API: {status}")` — calls `GET {api_url}/health`, shows green "Online" or red "Offline"
  7. Lazy imports: `import httpx` inside the submit handler (deferred, follows codebase pattern)
- **Mirror**: schemas.py:31-35 for response shape; state.py:16-20 for category constants
- **Validate**: `uv run --extra streamlit streamlit run ui/streamlit_app.py` launches without import errors (requires API running separately)

### Task 2: Update pyproject.toml

- **File**: `pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `[project.scripts]` entry for Streamlit:
  ```toml
  guardrails-ui = "streamlit.cli:main"
  ```
  No new dependencies needed — `httpx` is already in `[project.dependencies]`.
- **Mirror**: existing entry `guardrails-api = "guardrails.api.app:run"` at line 33
- **Validate**: `uv run guardrails-ui --help` shows streamlit help

### Task 3: Update .gitignore

- **File**: `.gitignore`
- **Action**: UPDATE
- **Implement**: Add `.streamlit/` to ignore Streamlit's local config directory (created on first run)
- **Validate**: `echo ".streamlit/" >> .gitignore && git diff .gitignore`

### Task 4: Docker infrastructure

- **Files**:
  - `docker/Dockerfile.api` — CREATE
  - `docker/Dockerfile.ui` — CREATE
  - `docker-compose.yml` — CREATE
- **Action**: CREATE
- **Implement**:

  **`docker/Dockerfile.api`** (multi-stage):
  ```dockerfile
  # Stage 1: pre-download ML models
  FROM python:3.12-slim AS model-download
  WORKDIR /models
  RUN pip install sentence-transformers transformers torch --quiet
  RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
  RUN python -c "from transformers import pipeline; pipeline('text-classification', model='protectai/deberta-v3-base-prompt-injection-v2')"

  # Stage 2: runtime
  FROM python:3.12-slim
  WORKDIR /app
  COPY --from=model-download /root/.cache /root/.cache
  COPY pyproject.toml uv.lock ./
  COPY guardrails/ guardrails/
  RUN pip install uv && uv sync --no-dev --frozen
  EXPOSE 8000
  CMD ["uv", "run", "guardrails-api"]
  ```

  **`docker/Dockerfile.ui`** (slim):
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  COPY pyproject.toml uv.lock ./
  COPY ui/ ui/
  RUN pip install uv && uv sync --no-dev --frozen --extra streamlit
  EXPOSE 8501
  CMD ["uv", "run", "streamlit", "run", "ui/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
  ```

  **`docker-compose.yml`**:
  ```yaml
  services:
    qdrant:
      image: qdrant/qdrant:latest
      ports: ["6333:6333"]
      volumes: ["qdrant_data:/qdrant/storage"]

    api:
      build:
        context: .
        dockerfile: docker/Dockerfile.api
      ports: ["8000:8000"]
      environment:
        - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
        - QDRANT_HOST=qdrant
      depends_on:
        qdrant:
          condition: service_started

    ingest:
      build:
        context: .
        dockerfile: docker/Dockerfile.api
      entrypoint: ["uv", "run", "python", "scripts/ingest_banking_kb.py"]
      environment:
        - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
        - QDRANT_HOST=qdrant
      depends_on:
        qdrant:
          condition: service_started
      profiles: ["ingest"]

    ui:
      build:
        context: .
        dockerfile: docker/Dockerfile.ui
      ports: ["8501:8501"]
      environment:
        - API_URL=http://api:8000
      depends_on:
        - api

  volumes:
    qdrant_data:
  ```
- **Validate**: `docker compose build` succeeds (both images); `docker compose run --rm ingest` ingests banking KB

### Task 5: CI pipeline

- **File**: `.github/workflows/ci.yml` — CREATE
- **Action**: CREATE
- **Implement**:
  ```yaml
  name: CI

  on:
    push:
      branches: [main, feature/*]
    pull_request:
      branches: [main]

  jobs:
    lint:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v5
        - uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        - run: uv sync --group dev
        - run: uv run ruff check .
        - run: uv run ruff format --check .

    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v5
        - uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        - run: uv sync --group dev
        - run: uv run pytest -m "not slow and not network" -q

    adversarial-smoke:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v5
        - uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        - run: uv sync --group dev
        - run: uv run pytest tests/adversarial/ -m "adversarial and not network" -q

    docker-build:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: docker compose build --parallel
  ```
- **Mirror**: standard GitHub Actions setup-uv pattern
- **Validate**: `ls .github/workflows/ci.yml` exists; grep for job names lint, test, adversarial-smoke, docker-build

### Task 6: Update README.md

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Update Quick Start section from the current curl-based instructions to `docker compose up`. Add a prereq section (`ANTHROPIC_API_KEY`, Docker). Keep the existing architecture diagram and curl commands as an alternative.
- **Validate**: `grep -q "docker compose up" README.md`

### Task 7: End-to-end verification

- **Action**: VERIFY
- **Implement**:
  1. `uv run ruff check .` — clean
  2. `uv run ruff format --check .` — clean
  3. `uv run pytest -m "not slow and not network" -q` — all fast tests pass
  4. `uv run pytest tests/adversarial/ -m "adversarial and not network" -q` — adversarial offline suite passes (≥80% block rate)
  5. `uv run --extra streamlit streamlit run ui/streamlit_app.py --server.headless=true` — Streamlit starts without error (headless mode, no browser)
  6. `docker compose build` — both images build successfully
- **Validate**: All commands exit 0

---

## Validation

```bash
# Lint
uv run ruff check .
uv run ruff format --check .

# Fast tests (CI-equivalent)
uv run pytest -m "not slow and not network" -q

# Adversarial offline tier
uv run pytest tests/adversarial/ -m "adversarial and not network" -q

# Streamlit smoke test (headless, just checks import)
uv run --extra streamlit streamlit run ui/streamlit_app.py --server.headless=true

# Docker build
docker compose build
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| **Docker image too large** (~2GB with HF models) | Multi-stage build pre-downloads models in a separate stage; model cache is ~1.2GB. Acceptable for local demo. Add `.dockerignore` to exclude `.venv/`, `.git/`, `__pycache__/`. |
| **Streamlit dependency conflict** | No new deps needed (`httpx` already in project). Streamlit pulls many transitive deps but they're isolated via `uv sync --extra streamlit`. |
| **CI pipeline runner timeout** | `adversarial-smoke` job runs the offline subset (~60s). `docker-build` can take 5-10min but runs in parallel with tests. No network-dependent tests in CI. |
| **Ingestion profile order** | `ingest` service in docker-compose runs as a one-shot; if Qdrant isn't ready, it fails. Mitigation: `depends_on: qdrant: condition: service_started` (not `healthy` — Qdrant doesn't expose a health endpoint by default). If race occurs, user re-runs `docker compose run --rm ingest`. |

---

## Acceptance Criteria

- [ ] Task 0: System prompt fix committed. `git log --oneline -1` shows `fix(SCRUM-12): pass chatbot system prompt to LLM provider`.
- [ ] Task 1: `uv run --extra streamlit streamlit run ui/streamlit_app.py --server.headless=true` starts without errors. Chat input renders. POSTing a message works when API is running.
- [ ] Task 2: `uv run guardrails-ui --help` shows Streamlit CLI help.
- [ ] Task 3: `.gitignore` contains `.streamlit/`.
- [ ] Task 4: `docker compose build` exits 0. `docker compose run --rm ingest` ingests banking KB (requires ANTHROPIC_API_KEY and Qdrant).
- [ ] Task 5: `.github/workflows/ci.yml` exists with 4 jobs (lint, test, adversarial-smoke, docker-build).
- [ ] Task 6: README.md Quick Start shows `docker compose up` flow.
- [ ] Task 7: All validation commands exit 0.
- [ ] All pre-SCRUM-12 tests still pass (`pytest -m "not slow and not network"`).
- [ ] Ruff lint + format clean.
