# Plan: SCRUM-7 — LangGraph StateGraph Pipeline (S-06)

## Summary

Build the central orchestrator for the guardrail system — a LangGraph `StateGraph` that wires the 4 validators, the LLM provider, and the structured logger into a bidirecional pipeline with conditional pass/fail branches. The pipeline exposes a `build_graph()` factory that accepts injectable validator/provider instances for testability, plus a config module that consumes `config.yaml` at runtime for thresholds, model names, and toggles.

## User Story

As a engenheiro de orquestração
I want a LangGraph StateGraph pipeline with nodes `input_guard → retrieve → generate → output_guard → block_log` and conditional edges for pass/fail
So that the entire bidirecional guardrail flow is centralized, testable, and ready for the FastAPI proxy (S-07) to call.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | pipeline (new), config (new), guardrails/__init__.py |
| Jira Issue | SCRUM-7 |
| Dependencies | S-01, S-02, S-03, S-04, S-05 (all COMPLETE) |
| Blocks | S-07 (FastAPI), S-08 (RAG replaces mock retrieve) |

---

## Patterns to Follow

### Validator dependency injection (mockable constructors)
```python
# SOURCE: guardrails/validators/compliance.py:22-25
def __init__(self, client=None, model="claude-haiku-4-5-20251001", timeout=5.0):
    self.client = client if client is not None else self._create_client(timeout)
```

### Fail-closed on exceptions
```python
# SOURCE: guardrails/validators/compliance.py:80-94
except Exception as e:
    return ValidatorResult(
        passed=False, category="compliance", score=1.0,
        details={"verdict": "fail", ..., "error": type(e).__name__},
    )
```

### Latency measurement with perf_counter
```python
# SOURCE: guardrails/validators/toxic.py:38-46
t0 = time.perf_counter()
...
latency_ms = (time.perf_counter() - t0) * 1000
```

### Structured logging with PII redaction
```python
# SOURCE: guardrails/observability/logger.py:60-65
log_blocked_event(direction="input", category="pii", severity="high",
                  input_text=text, extra=..., latency_ms=...)
```

### Validator protocol check
```python
# SOURCE: tests/unit/test_toxic.py:17-19
assert isinstance(validator, Validator)
```

### Mock helper pattern for tests
```python
# SOURCE: tests/unit/test_compliance.py:19-32
def _make_mock_validator(verdict="pass", ...):
    mock_client = MagicMock()
    mock_response = MagicMock()
    ...
    return ComplianceValidator(client=mock_client)
```

### Test speed gating
```python
# SOURCE: tests/unit/test_jailbreak.py:18-22
@pytest.mark.slow
@pytest.mark.skipif(bool(os.environ.get("SKIP_HEAVY_TESTS")), ...)
```

---

## Design Decisions

### Node architecture: closures inside `build_graph()`
Nodes are plain functions created as closures inside `build_graph()`, capturing injected validator/provider instances. This avoids class boilerplate while keeping DI clean.

```python
def build_graph(toxic=None, pii_input=None, pii_output=None, jailbreak=None,
                compliance=None, llm_provider=None, config=None):
    toxic_v = toxic or ToxicValidator(threshold=config.get("threshold", 0.7))
    pii_in_v = pii_input or PIIValidator(stage="input")
    ...

    def input_guard(state: GraphState) -> dict:
        ...
```

### Short-circuit: series, not parallel
Validators within each guard run sequentially; the first `passed=False` short-circuits and routes to `block_log`. Rationale: (a) compliance judge is expensive (~500ms) and should be last, (b) series is simpler to reason about, (c) latency of fast validators (regex <10ms, substring <5ms, detoxify <100ms) is negligible.

### Config: simple `yaml.safe_load` + env var expansion
Use `pyyaml` to load `config.yaml`, expand `${VAR}` patterns via a helper, return a `dict`. No pydantic model for now — keep it minimal. The validators already have sensible defaults; config just overrides them.

### Retrieve node: mock placeholder
Returns a hardcoded list of chunks about cartão Gold + investimentos. This is replaced in S-08 when Qdrant is wired in.

### `category` → `severity` mapping
```python
SEVERITY_MAP = {
    "jailbreak": "high",
    "compliance": "high",
    "pii_input": "high",
    "pii_output": "high",
    "toxicity": "medium",
}
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/pipeline/state.py` | CREATE | GraphState TypedDict + constants |
| `guardrails/pipeline/nodes.py` | CREATE | 5 node functions (input_guard, retrieve, generate, output_guard, block_log) |
| `guardrails/pipeline/graph.py` | CREATE | `build_graph()` factory — StateGraph + conditional edges |
| `guardrails/pipeline/__init__.py` | CREATE | Package init, exports `build_graph` and `GraphState` |
| `guardrails/config.py` | CREATE | Config loader — reads `config.yaml`, expands env vars |
| `guardrails/__init__.py` | UPDATE | Re-export pipeline, config |
| `config.yaml` | UPDATE | Remove TODO comment |
| `tests/unit/test_pipeline.py` | CREATE | Unit tests for pipeline nodes + graph compilation |
| `tests/unit/test_config.py` | CREATE | Unit tests for config loading |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Config module

- **File**: `guardrails/config.py`
- **Action**: CREATE
- **Implement**:
  - `load_config(path: str | None = None) -> dict` — reads `config.yaml` via `yaml.safe_load`, expands `${ENV_VAR}` placeholders using `os.environ.get()`, returns a plain dict
  - `get_config() -> dict` — module-level cached singleton (loaded once)
  - Default path: `config.yaml` in CWD
  - No pydantic model — keep it simple for MVP
- **Mirror**: `.claude/hooks/check_commit.py:49-53` — YAML loading pattern
- **Validate**: `python -c "from guardrails.config import load_config; c = load_config(); print(c.get('validators', {}).keys())"`

### Task 2: GraphState type + constants

- **File**: `guardrails/pipeline/state.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from __future__ import annotations
  from typing import TypedDict

  class GraphState(TypedDict):
      message: str                          # user's input
      retrieved_chunks: list[str]           # RAG results (mock for now)
      llm_response: str                     # LLM-generated response
      blocked: bool                         # whether any guardrail blocked
      block_category: str | None            # which category blocked
      block_details: dict | None            # details from blocking validator
      diagnostics: dict                     # latency breakdown, validators_run

  # Category constants
  CATEGORY_TOXICITY = "toxicity"
  CATEGORY_PII_INPUT = "pii_input"
  CATEGORY_PII_OUTPUT = "pii_output"
  CATEGORY_JAILBREAK = "jailbreak"
  CATEGORY_COMPLIANCE = "compliance"

  DIRECTION_INPUT = "input"
  DIRECTION_OUTPUT = "output"

  SEVERITY_MAP: dict[str, str] = {
      CATEGORY_JAILBREAK: "high",
      CATEGORY_COMPLIANCE: "high",
      CATEGORY_PII_INPUT: "high",
      CATEGORY_PII_OUTPUT: "high",
      CATEGORY_TOXICITY: "medium",
  }
  ```
- **Mirror**: `guardrails/validators/compliance.py:44-57` — module-level constant pattern
- **Validate**: `python -c "from guardrails.pipeline.state import GraphState; print(GraphState.__annotations__)"`

### Task 3: Pipeline nodes

- **File**: `guardrails/pipeline/nodes.py`
- **Action**: CREATE
- **Implement** 5 node functions (as closures inside a factory function OR as standalone functions that receive validators via closure):

  **Option (recommended):** `build_nodes()` factory that returns a dict of node functions:
  ```python
  def build_nodes(toxic, pii_input, pii_output, jailbreak, compliance, llm):
      ...
  ```

  **Each node:**
  - `input_guard(state)` — runs toxic → pii_input → jailbreak; short-circuits on first fail; logs via `log_blocked_event`/`log_passed_event`; returns `{blocked, block_category, block_details, diagnostics}`
  - `retrieve(state)` — returns `{retrieved_chunks: [placeholder string]}`
  - `generate(state)` — builds messages from system prompt + user message + chunks; calls `llm.complete()`; returns `{llm_response}`
  - `output_guard(state)` — runs toxic → pii_output → compliance on `llm_response`; short-circuits; logs; returns `{blocked, block_category, block_details, diagnostics}`
  - `block_log(state)` — returns `{message: fallback response}` (generic PT-BR mensagem de bloqueio)

  **Chatbot system prompt constant:**
  ```python
  CHATBOT_SYSTEM_PROMPT = """Você é um atendente bancário prestativo do Banco Seguro.
  Responda dúvidas sobre produtos bancários com base nos documentos fornecidos.
  Seja educado, claro e objetivo. Use português brasileiro.
  Se não souber a resposta, diga que não tem essa informação e sugira falar com um gerente."""
  ```

  **Fallback response constant:**
  ```python
  FALLBACK_RESPONSE = "Sua mensagem não pôde ser processada porque viola nossas políticas de segurança. Por favor, reformule sua pergunta."
  ```

- **Validate**: `python -c "from guardrails.pipeline.nodes import build_nodes; print(build_nodes.__doc__)"`

### Task 4: Graph builder

- **File**: `guardrails/pipeline/graph.py`
- **Action**: CREATE
- **Implement**:

  ```python
  def build_graph(
      toxic: ToxicValidator | None = None,
      pii_input: PIIValidator | None = None,
      pii_output: PIIValidator | None = None,
      jailbreak: JailbreakValidator | None = None,
      compliance: ComplianceValidator | None = None,
      llm_provider: AnthropicProvider | None = None,
      config: dict | None = None,
  ) -> CompiledStateGraph:
  ```

  - Creates default validator/provider instances if not injected (using config for thresholds)
  - Calls `build_nodes()` to get node functions
  - Builds `StateGraph(GraphState)`:
    ```
    input_guard ──[blocked?]──▶ block_log ──▶ END
         │
         └──[passed]──▶ retrieve ──▶ generate ──▶ output_guard ──[blocked?]──▶ block_log ──▶ END
                                                         │
                                                         └──[passed]──▶ END
    ```
  - Sets entry point, compiles, returns
  - Router functions for conditional edges:
    ```python
    def route_after_input(state: GraphState) -> str:
        return "block_log" if state["blocked"] else "retrieve"

    def route_after_output(state: GraphState) -> str:
        return "block_log" if state["blocked"] else "__end__"
    ```

- **Mirror**: `guardrails/validators/compliance.py:22-25` — constructor dependency injection pattern
- **Validate**: `python -c "from guardrails.pipeline.graph import build_graph; g = build_graph(); print(type(g).__name__)"`

### Task 5: Package wiring

- **File**: `guardrails/pipeline/__init__.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from .graph import build_graph
  from .state import (
      CATEGORY_COMPLIANCE, CATEGORY_JAILBREAK, CATEGORY_PII_INPUT,
      CATEGORY_PII_OUTPUT, CATEGORY_TOXICITY, DIRECTION_INPUT,
      DIRECTION_OUTPUT, SEVERITY_MAP, GraphState,
  )

  __all__ = [
      "GraphState", "build_graph",
      "CATEGORY_TOXICITY", "CATEGORY_PII_INPUT", "CATEGORY_PII_OUTPUT",
      "CATEGORY_JAILBREAK", "CATEGORY_COMPLIANCE",
      "DIRECTION_INPUT", "DIRECTION_OUTPUT", "SEVERITY_MAP",
  ]
  ```

- **File**: `guardrails/__init__.py`
- **Action**: UPDATE
- **Add** after existing imports:
  ```python
  from guardrails.config import load_config
  from guardrails.pipeline import build_graph, GraphState
  ```
  Add to `__all__`: `"build_graph"`, `"GraphState"`, `"load_config"`

- **File**: `config.yaml`
- **Action**: UPDATE
- **Change**: Remove the `# TODO: consumed by S-06 LangGraph pipeline — not yet read at runtime` comment line (line 1)

### Task 6: Tests

- **File**: `tests/unit/test_pipeline.py`
- **Action**: CREATE
- **Test structure**:
  - `test_graph_builds_and_compiles()` — `build_graph()` returns a compiled graph
  - `test_happy_path_flow()` — benign message: passes input_guard → retrieve → generate → output_guard → END; `blocked=False`
  - `test_input_guard_blocks_pii()` — message with PII: blocks at input_guard, routes to block_log, returns fallback
  - `test_input_guard_blocks_jailbreak()` — message with jailbreak keyword: blocks at input_guard
  - `test_input_guard_blocks_toxic()` — toxic message: blocks at input_guard
  - `test_output_guard_blocks_compliance()` — output with R2 violation (mock judge): blocks at output_guard
  - `test_output_guard_blocks_pii()` — output with PII: blocks at output_guard
  - `test_block_log_returns_fallback()` — blocked state produces fallback response
  - `test_diagnostics_populated_on_pass()` — benign path: diagnostics has `input_guard_ms`, `retrieve_ms`, `generate_ms`, `output_guard_ms`
  - `test_graph_state_defaults()` — empty GraphState has correct default types
  - **Test pattern**: mock validators with `MagicMock`, use `_make_mock_*()` helpers following existing patterns; mock `llm_provider.complete()` to return a canned response; full graph execution via `graph.invoke({"message": ...})`

- **File**: `tests/unit/test_config.py`
- **Action**: CREATE
- **Test structure**:
  - `test_load_config_returns_dict()` — loads existing config.yaml successfully
  - `test_env_var_expansion()` — `${VAR}` patterns expanded from os.environ
  - `test_missing_file_returns_empty()` — nonexistent path returns empty dict (graceful degradation)
  - `test_default_path_is_config_yaml()` — `load_config()` without args uses CWD/config.yaml

---

## Validation

```bash
# Type check (basic import validation)
python -c "from guardrails.pipeline import build_graph, GraphState; print('pipeline ok')"
python -c "from guardrails.config import load_config; print('config ok')"

# Lint
ruff check guardrails/pipeline/ guardrails/config.py tests/unit/test_pipeline.py tests/unit/test_config.py

# Format
ruff format --check guardrails/pipeline/ guardrails/config.py tests/unit/test_pipeline.py tests/unit/test_config.py

# Unit tests (fast only, no model loads)
python -m pytest tests/unit/test_pipeline.py tests/unit/test_config.py -v

# Unit tests including slow (local only, not CI)
SKIP_HEAVY_TESTS=1 python -m pytest tests/unit/ -v
```

---

## Acceptance Criteria

- [ ] `build_graph()` compiles a `StateGraph` with 5 nodes and conditional edges
- [ ] Benign message flows: input_guard → retrieve → generate → output_guard → END; `blocked=False`
- [ ] Input with PII blocks at input_guard → block_log; returns fallback response
- [ ] Input with jailbreak keyword blocks at input_guard
- [ ] Output with compliance violation blocks at output_guard → block_log
- [ ] Output with PII blocks at output_guard
- [ ] Fallback response returned when blocked (generic PT-BR message)
- [ ] Diagnostics populated on pass path with per-stage latency breakdown
- [ ] `load_config()` reads `config.yaml`, expands `${ANTHROPIC_API_KEY}` from env
- [ ] All pipeline nodes accept injected validator/provider instances (testability)
- [ ] Ruff lint + format pass
- [ ] Tests pass with `SKIP_HEAVY_TESTS=1`

---

## Risks

| Risk | Mitigation |
|------|------------|
| LangGraph API mismatch (version 0.4 vs 1.x) | LangGraph 1.2.2 is locked in `uv.lock` — verify API surface before coding. The `StateGraph`, `add_node`, `add_conditional_edges` API is stable since 0.4. |
| Config YAML missing at runtime | `load_config()` returns empty dict gracefully; validators use their own defaults. |
| Short-circuit in input_guard skips output_guard entirely (correct behavior) | This is intentional — blocked input never reaches LLM. Verify in tests. |
| ComplianceValidator real API call in integration tests | All pipeline unit tests use `MagicMock`-injected validators. No real API calls. |
