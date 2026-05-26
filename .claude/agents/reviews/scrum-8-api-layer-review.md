# Code Review: Scrum-8 — FastAPI + Chat Endpoint

**Scope**: `guardrails/api/`, `tests/api/`, modified `pyproject.toml`, modified `README.md`, deleted `.buddy/`
**Recommendation**: APPROVE

## Summary

New FastAPI proxy layer (`POST /chat`, `GET /health`) with 12 passing tests covering all 5 acceptance criteria. Architecture follows the project's factory + lifespan pattern. Test fixtures correctly decouple from real models via monkeypatching. Pre-existing compliance/jailbreak test failures (slow _real_api tests) are unrelated.

## Issues Found

### Critical

None.

### High Priority

- **`guardrails/api/app.py:88` — Sync `def` handler inside async middleware may break structlog contextvars propagation.** The `request_id_middleware` is async and calls `bind_contextvars` in the async event loop, but `chat(req, request)` is a sync `def` handler — FastAPI runs sync handlers in a threadpool thread, so structlog's `contextvars` binding from the middleware won't propagate into the handler. `clear_contextvars` in the `finally` block will also clear from the wrong context. **Fix**: make `chat` an `async def` so it runs on the main loop, or use `structlog.threadlocal.bind_threadlocal` instead (though that's discouraged by structlog docs for asyncio).

### Medium Priority

- **`guardrails/api/app.py:136-138` — Health endpoint accesses `._model`, `._pipeline`, `.client` as private attributes.** This couples `/health` to internal implementation details of each validator/provider. If a validator refactors its model loading (e.g., lazy init → async), the health endpoint silently breaks. **Recommendation**: add a public `is_loaded` property or method to each validator/provider class, or use `Protocol` with an `is_healthy()` method.

- **`guardrails/api/app.py:106` — `sum(..., total)` silently drops non-numeric diagnostic values.** If a diagnostic key has a string or `None`, it's excluded from the total without warning. **Recommendation**: explicitly handle `None` by filtering `(v for v in diag.values() if v is not None and isinstance(v, (int, float)))` — no behavioral change but documents intent.

- **`tests/api/conftest.py:111` — `lambda cfg: components` ignores config argument.** If `_create_components`'s signature ever changes, this patched lambda will silently return stale components rather than fail at import time. **Recommendation**: match the mock's signature: `lambda cfg: components` is fine for now, but add a comment documenting this intentional bypass.

- **`guardrails/api/schemas.py:23` — Bare `dict` instead of `dict[str, Any]`.** Pydantic accepts both, but the rest of the codebase uses `dict[str, Any]` (see `validators/base.py:24`). **Recommendation**: use `dict[str, Any]` for consistency.

### Suggestions

- **`guardrails/api/app.py:59-69` — Unpacked variables `toxic, jailbreak, compliance, llm` are only used to set `app.state`.** This is fine, but consider using a dataclass or named tuple from `_create_components` to avoid positional unpacking fragility if more components are added.

- **`tests/api/test_chat_endpoint.py:101` — UUID validation via `uuid.UUID(x)` with bare exception.** If the value is not a valid UUID, `uuid.UUID()` raises `ValueError` which is not caught by pytest's `assert` introspection, making the error message less useful. **Recommendation**: `assert isinstance(uuid.UUID(request_id), uuid.UUID)` or add a descriptive error message.

## Validation Results

| Check | Status |
|-------|--------|
| Ruff Lint | PASS |
| API Tests (12) | PASS |
| Full Suite (146) | 20 FAIL |

**Note**: The 20 failures are all in pre-existing `_real_api` and `@pytest.mark.slow` tests (compliance judge real API calls fail with `TypeError`, jailbreak DeBERTa model mismatch) — they are **unrelated to this scope** and are skipped when `SKIP_HEAVY_TESTS=1`.

## What's Good

- **Test architecture**: `make_client` factory fixture is clean — allows per-test validator behaviour injection. Following the `_build_mock_components` pattern from `tests/unit/test_pipeline.py` correctly.
- **Fail-closed testing**: Explicit test (`test_fail_closed.py`) verifies that compliance timeout/error becomes HTTP 200 with `blocked=True`, not a 500. This directly addresses building-rigorously §2.
- **Request ID tracing**: Middleware echoes `x-request-id` header through diagnostics — good observability practice for distributed tracing.
- **Pydantic validation**: `ChatRequest.message` has `min_length=1, max_length=4000` — bounds-checked at the boundary.
- **Config cache cleared in tests**: `monkeypatch.setattr(guardrails.config, "_config_cache", None)` ensures clean config state across test invocations.

## Recommendation

Address the **structlog contextvars + sync def** issue (High) before merging — it will cause `request_id` to be missing from all downstream handler logs, breaking the observability design. The rest are minor improvements.

**APPROVE** once the contextvars issue is resolved.
