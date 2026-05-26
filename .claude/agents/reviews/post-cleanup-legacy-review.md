# Code Review: Post-Cleanup + New Modules (SCRUM-5/6)

**Scope**: Unstaged changes (removal of `guardrails_legacy.py`, cleanup of `guardrails/__init__.py`, new `adapters/` and `observability/` modules, updated `pyproject.toml`, `config.yaml`, `README.md`)
**Recommendation**: **NEEDS WORK** (2 high-priority issues before merge)

## Summary

The cleanup removed ~308 lines of dead PoC code and the legacy bridge in `__init__.py`. Two new modules arrived (`guardrails/adapters/` — LLM provider abstraction, `guardrails/observability/` — structlog JSON logger) with solid test coverage. The `pyproject.toml` was updated with correct dependencies for the new architecture. Two high-priority issues were found: dead code in the logger and a model name mismatch in config.

## Issues Found

### High Priority

**H1 — Dead code in `guardrails/observability/logger.py:73-74`**
```python
if input_text is not None:
    sanitize_for_log(input_text)  # ← result discarded, no side effects
```
The return value of `sanitize_for_log()` is never stored, logged, or returned. The function is pure (no mutation, no IO). This is genuinely dead code — either remove the call, or log the sanitized text instead of (or alongside) the raw hash. Since the `input_hash` is a one-way SHA-256 of the first 200 chars, hashing raw PII is acceptable; the `_compute_input_hash` is the intended mechanism.

**Fix**: Remove lines 73-74, or replace with logic that logs the sanitized text for debugging.

---

**H2 — `config.yaml` model name mismatch with `guardrails/adapters/llm.py`**
- `config.yaml` line 2: `model: "claude-sonnet-4-6"`
- `guardrails/adapters/llm.py` line 14: `DEFAULT_MODEL = "claude-sonnet-4-6-20251105"`

The date suffix `-20251105` is semantically significant — it pins a specific model version. The config file uses a floating alias that Anthropic resolves at request time, which may change. Two different consumers could get different model versions.

**Fix**: Align to one canonical name. Recommend keeping the dated version in both places for reproducibility. Change `config.yaml` to `model: "claude-sonnet-4-6-20251105"`.

---

### Medium Priority

**M1 — `config.yaml` is not consumed by any code in the current codebase**
The file has sections for `validators.toxicity`, `validators.pii`, `validators.jailbreak`, `validators.compliance`, `qdrant`, `embedding`, and `logging` — but no Python module reads this file. The Anthropic SDK reads `ANTHROPIC_API_KEY` from the environment directly. The `validators` are configured via constructor parameters (DI). This is forward-looking config that will be consumed by the LangGraph pipeline (S-06), but creates a gap: the config file says one thing, the actual runtime config says another.

**Fix**: Either create a settings loader (`pydantic-settings` or `guardrails/config.py`) that reads `config.yaml` before building the pipeline, or remove the config sections until S-06. For now, add a `# TODO: consumed by S-06 LangGraph pipeline` comment to `config.yaml`.

---

**M2 — `main.py` is a dead stub** (3 lines, prints "Hello from llm-guardrails-tutorial!")
No `[project.scripts]` entry point references it. No module imports it. It's scaffolding from `uv init`.

**Fix**: Delete `main.py`.

---

**M3 — `asyncio_mode = "auto"` in `pyproject.toml:28` triggers PytestConfigWarning**
```
Unknown config option: asyncio_mode
```
No async tests exist yet. The setting is valid for `pytest-asyncio` but causes a warning on every run until `asyncio_mode` is actually needed.

**Fix**: Remove `asyncio_mode = "auto"` from `pyproject.toml` and add it when async tests land.

---

**M4 — `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` present at repo root**
These are build artifacts. `.gitignore` already covers `__pycache__/` but not `.pytest_cache/` or `.ruff_cache/`.

**Fix**: Add `.pytest_cache/` and `.ruff_cache/` to `.gitignore`.

---

**M5 — `guardrails/__init__.py` does not re-export `adapters` and `observability`**
These are sibling subpackages of `guardrails/`. Users must know the full path:
```python
from guardrails.adapters import AnthropicProvider  # OK
from guardrails import AnthropicProvider  # AttributeError
```

**Fix**: Either add re-exports to `guardrails/__init__.py` (consistent with how `validators` are re-exported), or document the import paths clearly.

---

### Suggestions

**S1 — `guardrails/observability/logger.py:73-74` dead code is also a regression risk**
Even after removing the dead call, the intent of the original author was clearly to sanitize PII from logs. Consider adding a `sanitized_snippet` field to the log event with the first 100 chars of sanitized text for debugging.

**S2 — `AnthropicProvider.complete()` swallow-exception returns `""` (empty string)**
`complete_with_tools()` returns `None` on error. The caller has no way to distinguish "empty response" from "error". Consider a `result` wrapper type or a distinct sentinel.

**S3 — Duplicated PII regex patterns**
PII regexes are defined in two places:
- `guardrails/validators/pii.py:18-23` (PII_PATTERNS)
- `guardrails/observability/logger.py:26-31` (_PII_PATTERNS)

These are identical but independent. A change to one without the other creates a security gap (logger allows a PII pattern through that the validator blocks). Consider extracting to `guardrails/_pii_patterns.py` or similar shared location.

**S4 — `guardrails/adapters/llm.py` `complete_with_tools` hardcodes `max_tokens=512`**
Unlike `complete()` which surfaces `max_tokens` as a parameter, `complete_with_tools()` hardcodes 512. The `ComplianceValidator` in `guardrails/validators/compliance.py:86` also hardcodes 512 — so there's no inconsistency in practice, but the adapter should expose the parameter for future tool-using callers.

## Validation Results

| Check | Status |
|-------|--------|
| Lint (ruff) | **PASS** |
| Tests (fast) | **PASS** — 81 passed, 3 xfailed |
| Imports | **PASS** — all modules load correctly |

## What's Good

- **`guardrails_legacy.py` deletion** was overdue — 308 lines of superseded code, keyword-based intent detection, no DeBERTa, no compliance judge. Clean cut.
- **`pyproject.toml` deps** are correct for the new architecture (`langgraph`, `fastapi`, `structlog`, `qdrant-client`, `sentence-transformers`)
- **`guardrails/adapters/llm.py`** protocol + DI pattern mirrors `Validator` protocol exactly — consistent, testable, mock-friendly
- **Logger tests** in `test_logger.py` are thorough: schema completeness, extra fields, edge cases (empty, None), security (PII not in hash)
- **LLM provider tests** cover protocol check, parameter passthrough, fail-closed on exception — good contract coverage
- **`README.md` rewrite** eliminates all references to Langfuse, Voyage, guardrails-ai, and guardrails-ai Hub validators — accurate to current architecture
- **`.buddy/` outdated warnings** prevent confusion without deleting the auto-generated docs

## Recommendation

The two **high-priority issues** (H1 dead code, H2 model name mismatch) should be fixed before merging. The medium-priority items (M1-M5) are acceptable as debt-in-code if time is tight, but M3 (pytest warning) and M4 (cache dirs) are trivial wins.

**TL;DR**: Fix H1 H2 → APPROVE. Everything else is polish or planned debt.
