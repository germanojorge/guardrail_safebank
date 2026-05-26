# Plan: SCRUM-6 — LLM Adapter + Structured JSON Logger

## Summary

Criar dois módulos independentes em diretórios novos (`guardrails/adapters/` e `guardrails/observability/`) seguindo os patterns estabelecidos pelos validators existentes. O `LLMProvider` protocol + `AnthropicProvider` abstrai o SDK Anthropic num adapter fino para o pipeline LangGraph (S-06). O logger estrutural (`structlog`) emite eventos JSON padronizados para stdout com schema fixo de 8 campos, garantindo que valores PII nunca vazem em logs (só o tipo da entidade).

## User Story

As a engenheiro de orquestração
I want um LLM provider adapter e logger estruturado JSON
So that o pipeline LangGraph (S-06) possa chamar o Claude de forma abstraída e cada bloqueio gere eventos JSON pesquisáveis via `docker logs api | jq`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | guardrails/adapters, guardrails/observability, pyproject.toml |
| Jira Issue | SCRUM-6 |

---

## Patterns to Follow

### Naming — Protocol + Concrete Class

```
// SOURCE: guardrails/validators/base.py:27-33
@runtime_checkable
class Validator(Protocol):
    name: str

    def run(
        self, text: str, context: Mapping[str, Any] | None = None
    ) -> ValidatorResult: ...
```

```
// SOURCE: guardrails/validators/compliance.py:44-45
class ComplianceValidator:
    name = "compliance"
```

**Apply**: `LLMProvider` protocol (like `Validator`) + `AnthropicProvider` (like `ComplianceValidator`).

### Constructor — Dependency Injection for Testability

```
// SOURCE: guardrails/validators/compliance.py:47-55
def __init__(
    self,
    client=None,
    model: str = "claude-haiku-4-5-20251001",
    timeout: float = 5.0,
) -> None:
    self.client = client if client is not None else self._create_client(timeout)
    self.model = model
    self.timeout = timeout
```

**Apply**: `AnthropicProvider.__init__` aceita `client=None`, cria real se não injetado.

### Lazy Import — Avoid Top-Level SDK Import

```
// SOURCE: guardrails/validators/compliance.py:57-61
@staticmethod
def _create_client(timeout: float = 5.0):
    from anthropic import Anthropic

    return Anthropic(timeout=timeout)
```

**Apply**: `AnthropicProvider._create_client()` importa `Anthropic` lazy.

### Error Handling — Fail-Closed, Never Re-Raise

```
// SOURCE: guardrails/validators/compliance.py:121-135
except Exception as e:
    return ValidatorResult(
        passed=False,
        ...
        details={
            ...
            "error": type(e).__name__,
        },
        ...
    )
```

**Apply**: `AnthropicProvider.complete()` captura `Exception`, loga `type(e).__name__`, retorna/relança string vazia com erro no log.

### Module Docstring — List Output Keys

```
// SOURCE: guardrails/validators/pii.py:1-9
"""
PIIValidator — detects PII in PT-BR text using regex patterns.

`details` keys populated by `run()`:
- `entities`: dict mapping entity type to list of (start, end) span tuples
...
"""
```

**Apply**: Each new file gets a module-level docstring documenting its exported symbols.

### Import Style — Absolute Cross-Package

```
// SOURCE: guardrails/validators/compliance.py:21-22
from guardrails.compliance.prompt import build_system_prompt
from guardrails.validators.base import ValidatorResult
```

**Apply**: `from guardrails.adapters.llm import LLMProvider` style.

### Test — Mock Pattern for Client

```
// SOURCE: tests/unit/test_compliance.py:23-39
def _make_mock_validator(...) -> ComplianceValidator:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.input = { ... }
    mock_response.content = [mock_tool_use]
    mock_response.stop_reason = stop_reason
    mock_client.messages.create.return_value = mock_response
    return ComplianceValidator(client=mock_client)
```

**Apply**: `_make_mock_provider()` cria `MagicMock()` client, setta `return_value`, injeta no `AnthropicProvider`.

### Test — Skip Gate for Heavy/Real API Tests

```
// SOURCE: tests/unit/test_compliance.py:144-148
@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping real API tests",
)
```

**Apply**: Logger tests marcados como `@pytest.mark.slow` se testam stdout real.

### Test — Section Header Comments

```
// SOURCE: tests/unit/test_jailbreak.py:71-73
# ---------------------------------------------------------------------------
# Layer 1 — substring fast-path
# ---------------------------------------------------------------------------
```

**Apply**: Same dash-separated section comments in test files.

### Package `__init__.py` — Explicit Re-Exports with `__all__`

```
// SOURCE: guardrails/validators/__init__.py:1-14
from .base import Validator, ValidatorResult
...

__all__ = [
    "ComplianceValidator",
    ...
]
```

**Apply**: `guardrails/adapters/__init__.py` and `guardrails/observability/__init__.py` follow same pattern.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/adapters/__init__.py` | CREATE | Package marker + re-exports |
| `guardrails/adapters/llm.py` | CREATE | `LLMProvider` protocol + `AnthropicProvider` |
| `guardrails/observability/__init__.py` | CREATE | Package marker + re-exports |
| `guardrails/observability/logger.py` | CREATE | `structlog` wrapper with fixed schema |
| `pyproject.toml` | UPDATE | Add `structlog >= 24.4` dependency |
| `tests/unit/test_llm_provider.py` | CREATE | Provider contract tests |
| `tests/unit/test_logger.py` | CREATE | Logger schema + security tests |
| `guardrails/__init__.py` | UPDATE | Re-export new public symbols (optional, only if needed at top-level) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add structlog dependency

- **File**: `pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `"structlog>=24.4"` to the `dependencies` list (keep alphabetical: after `"pyyaml>=6.0.3"`, before `"torch>=2.2"`)
- **Mirror**: `guardrails/validators/compliance.py:58` — lazy import pattern (structlog is imported inside functions, never at top level except in logger.py)
- **Validate**: `uv sync` or `pip install -e .` resolves without error

### Task 2: Create `guardrails/adapters/llm.py`

- **File**: `guardrails/adapters/llm.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring documenting `LLMProvider` protocol and `AnthropicProvider`
  - `LLMProvider` protocol with `@runtime_checkable`:
    - Method `complete(messages: list[dict], model: str, **kwargs) -> str`
  - `AnthropicProvider`:
    - `__init__(self, client=None, model="claude-sonnet-4-6", timeout=10.0)` — dependency injection
    - `_create_client()` lazy-imports `Anthropic` (matching compliance.py:57-61)
    - `complete(messages, model=None, temperature=0.3, max_tokens=1024)` — wraps `self.client.messages.create()`, extracts `content[0].text`
    - `complete_with_tools(messages, tools, tool_choice, model=None, system=None, temperature=0.0)` — for compliance judge usage (returns raw response object for tool parsing)
    - Error handling: fail-closed, catches `Exception`, logs `type(e).__name__`, returns empty string
  - Constants section: `DEFAULT_MODEL`, `JUDGE_MODEL`
- **Mirror**: `guardrails/validators/base.py:27-33` (Protocol), `guardrails/validators/compliance.py:47-61` (DI + lazy import), `guardrails/validators/compliance.py:121-135` (fail-closed)
- **Validate**: `python -c "from guardrails.adapters.llm import LLMProvider, AnthropicProvider; print('OK')"`

### Task 3: Create `guardrails/adapters/__init__.py`

- **File**: `guardrails/adapters/__init__.py`
- **Action**: CREATE
- **Implement**: Re-export `LLMProvider`, `AnthropicProvider` with `__all__`
- **Mirror**: `guardrails/validators/__init__.py:1-14`
- **Validate**: `python -c "from guardrails.adapters import LLMProvider, AnthropicProvider; print('OK')"`

### Task 4: Create `guardrails/observability/logger.py`

- **File**: `guardrails/observability/logger.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring documenting log schema
  - `setup_logging()` — configures structlog once (processors: timestamper, add_log_level, JSON renderer)
  - `log_blocked_event(*, direction, category, severity, rule_violated=None, latency_ms=None, input_text=None, extra=None)` — main public function
    - Computes `input_hash` = `sha256(input_text[:200]).hexdigest()` (never raw input)
    - Builds event dict: `timestamp`, `event="validator.blocked"`, `direction`, `category`, `severity`, `rule_violated`, `input_hash`, `latency_ms`
    - Merges `extra` dict if provided (for `layer_caught`, `substring_match_count`, etc.)
    - Calls `structlog.get_logger().info(...)`
  - `log_passed_event(*, direction, category, latency_ms, input_text=None, extra=None)` — for non-blocked events (diagnostics)
  - `sanitize_for_log(text: str) -> str` — strips PII patterns (uses `PII_PATTERNS` regex, replaces matches with `[REDACTED_<type>]`)
  - Constants: `INPUT_HASH_MAX_CHARS = 200`, `LOGGER_NAME = "guardrails"`
  - Never logs PII values: `input_hash` used instead of raw text; entity type logged but not value
- **Mirror**: `guardrails/validators/base.py:1-9` (docstring lists keys), `guardrails/validators/pii.py:18-23` (PII_PATTERNS reuse)
- **Validate**: `python -c "from guardrails.observability.logger import setup_logging, log_blocked_event; print('OK')"`

### Task 5: Create `guardrails/observability/__init__.py`

- **File**: `guardrails/observability/__init__.py`
- **Action**: CREATE
- **Implement**: Re-export `setup_logging`, `log_blocked_event`, `log_passed_event` with `__all__`
- **Mirror**: `guardrails/adapters/__init__.py` pattern (same structure)
- **Validate**: `python -c "from guardrails.observability import setup_logging, log_blocked_event; print('OK')"`

### Task 6: Create `tests/unit/test_llm_provider.py`

- **File**: `tests/unit/test_llm_provider.py`
- **Action**: CREATE
- **Implement**:
  - Section: Protocol check — `isinstance(AnthropicProvider(), LLMProvider)`
  - Section: Happy path — mock `messages.create()` returns content with text, assert `complete()` returns that text
  - Section: Error path — mock raises `RuntimeError`, assert `complete()` returns `""` (fail-closed)
  - Section: Model passthrough — verify model arg reaches `messages.create(model=...)`
  - Section: Temperature passthrough — verify temperature arg reaches SDK
  - Helper: `_make_mock_provider(response_text="Hello")` creates `MagicMock()` client
- **Mirror**: `tests/unit/test_compliance.py:23-39` (mock helper), `tests/unit/test_compliance.py:115-122` (error test), `tests/unit/test_compliance.py:125-136` (details keys check)
- **Validate**: `python -m pytest tests/unit/test_llm_provider.py -v`

### Task 7: Create `tests/unit/test_logger.py`

- **File**: `tests/unit/test_logger.py`
- **Action**: CREATE
- **Implement**:
  - Configures structlog to print to `io.StringIO` for capture
  - Section: Schema completeness — `log_blocked_event()` emits JSON with all required keys: `timestamp`, `event`, `direction`, `category`, `severity`, `input_hash`, `latency_ms`
  - Section: `input_hash` format — verify SHA-256 hex digest (64 hex chars), deterministic for same input
  - Section: PII security — when `input_text` contains CPF/email/card, `input_hash` is hash not raw value; entity type appears but value never leaks
  - Section: Extra fields pass-through — `layer_caught`, `substring_match_count` appear in output
  - Section: `sanitize_for_log` strips PII patterns correctly
  - Section: `log_passed_event` — different event name, passes through
  - Section: No exception on empty input — empty string doesn't crash
  - Uses `capsys` fixture or `io.StringIO` to capture stdout
- **Mirror**: `tests/unit/test_pii.py:102-123` (PII value leak detection pattern), `tests/unit/test_compliance.py:125-136` (required keys check)
- **Validate**: `python -m pytest tests/unit/test_logger.py -v`

---

## Validation

```bash
# Check structlog resolves
uv sync 2>&1 | head -5

# Verify imports
python -c "from guardrails.adapters import AnthropicProvider; from guardrails.observability import log_blocked_event; print('OK')"

# Run all new tests
python -m pytest tests/unit/test_llm_provider.py tests/unit/test_logger.py -v

# Run full test suite to ensure no regressions
python -m pytest tests/unit/ -v --ignore=tests/unit/test_compliance.py --ignore=tests/unit/test_toxic.py --ignore=tests/unit/test_jailbreak.py

# Lint check new files
ruff check guardrails/adapters/ guardrails/observability/ tests/unit/test_llm_provider.py tests/unit/test_logger.py

# Type check (if mypy is configured, else skip)
# ruff already covers basic hygiene
```

---

## Acceptance Criteria

- [ ] Task 1: `structlog` added to `pyproject.toml`, installs cleanly
- [ ] Task 2: `guardrails/adapters/llm.py` with `LLMProvider` protocol + `AnthropicProvider` complete
- [ ] Task 3: `guardrails/adapters/__init__.py` re-exports with `__all__`
- [ ] Task 4: `guardrails/observability/logger.py` with `setup_logging()`, `log_blocked_event()`, `log_passed_event()`, `sanitize_for_log()`
- [ ] Task 5: `guardrails/observability/__init__.py` re-exports with `__all__`
- [ ] Task 6: `test_llm_provider.py` — protocol check, happy path, error fail-closed, model/temperature passthrough
- [ ] Task 7: `test_logger.py` — schema completeness, `input_hash` format, PII never in value, extra fields passthrough, `sanitize_for_log`
- [ ] All tests pass
- [ ] Ruff lint passes on new files
- [ ] No PII value leaks in log output (verified by test `_assert_no_raw_pii_in_details`-style check)
