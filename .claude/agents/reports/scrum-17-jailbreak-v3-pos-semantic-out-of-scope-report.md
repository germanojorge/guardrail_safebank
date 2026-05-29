# Implementation Report

**Plan**: `scrum-17-jailbreak-v3-pos-semantic-out-of-scope.plan.md`
**Branch**: `feature/scrum-17-jailbreak-v3-pos-semantic-out-of-scope`
**Status**: COMPLETE

## Summary

Refactored `JailbreakValidator` from 2-layer to 4-layer layered defense with early-exit (L1a regex → L1b POS tagger → L1c semantic index → L2 Prompt-Guard-2). Created `OutOfScopeValidator` with seed-based cosine similarity. Integrated both into the pipeline with `out_of_scope` as the last input guard validator.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Refactor jailbreak.py → 4-layer defense | `guardrails/validators/jailbreak.py` | ✅ |
| 2 | Create OutOfScopeValidator | `guardrails/validators/out_of_scope.py` | ✅ |
| 3 | Integrate into pipeline | `state.py`, `nodes.py`, `graph.py`, `app.py`, `__init__.py` | ✅ |
| 4 | Create build scripts | `scripts/build_jailbreak_index.py`, `scripts/build_outofscope_seeds.py` | ✅ |
| 5 | Write/update tests | `tests/unit/test_jailbreak.py`, `tests/unit/test_out_of_scope.py` | ✅ |
| 6 | Docker & dependencies | `docker/Dockerfile.models` | ✅ |
| 7 | Config & Limitations | `config.yaml`, `LIMITATIONS.md` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Ruff lint | ✅ (0 errors) |
| Ruff format | ✅ (all formatted) |
| Tests (fast) | ✅ (218 passed, 56 skipped, 0 failures) |
| API tests | ✅ (12 passed) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `guardrails/validators/jailbreak.py` | UPDATE | +555/-xxx (rewrite) |
| `guardrails/validators/out_of_scope.py` | CREATE | +200 |
| `guardrails/validators/__init__.py` | UPDATE | +2 |
| `guardrails/pipeline/state.py` | UPDATE | +2 |
| `guardrails/pipeline/nodes.py` | UPDATE | +4 |
| `guardrails/pipeline/graph.py` | UPDATE | +2 |
| `guardrails/api/app.py` | UPDATE | +14/-x |
| `config.yaml` | UPDATE | +14/-x |
| `docker/Dockerfile.models` | UPDATE | +8/-x |
| `scripts/build_jailbreak_index.py` | CREATE | +120 |
| `scripts/build_outofscope_seeds.py` | CREATE | +95 |
| `LIMITATIONS.md` | UPDATE | +50/-x |
| `tests/unit/test_jailbreak.py` | UPDATE | +410/-xxx (rewrite) |
| `tests/unit/test_out_of_scope.py` | CREATE | +275 |
| `tests/fixtures/jailbreak_semantic.py` | CREATE | +18 |
| `tests/api/conftest.py` | UPDATE | +4 |
| `tests/api/test_health_endpoint.py` | UPDATE | +8/-x |
| `tests/unit/test_pipeline.py` | UPDATE | +11/-x |

## Deviations from Plan

1. **POS tagger vector access**: The plan specified using `nlp.vocab.vectors` for token vector lookups, but spaCy's `Vectors` table doesn't support string key lookup via `in` or `[]`. Changed to use `nlp.vocab[token].vector` (Lexeme API) which correctly resolves word vectors.

2. **Test mocks**: POS tagger tests that required loading spaCy `pt_core_news_lg` (~500MB) are gated behind `SKIP_POS_TESTS` env var for faster CI runs, rather than unconditionally requiring the model.

3. **OutOfScope mock design**: The seed-based mock for `OutOfScopeValidator` tests uses a custom `_SeedAwareMock` class that returns different vectors based on call order (constructor seed calls vs. runtime query calls), replacing the initial counter-based approach that couldn't distinguish single-item seed lists from query calls.

4. **API test conftest**: Updated `_build_mock_components` in `tests/api/conftest.py` to include `mock_out_of_scope` in both the `build_graph` call and return tuple, matching the new 9-element unpacking in `app.py`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/unit/test_jailbreak.py` | 23 fast + 12 slow (regex, POS, semantic, prompt_guard, details contract, layer disabled, fail-open) |
| `tests/unit/test_out_of_scope.py` | 8 fast + 3 slow (in-scope pass, out-of-scope block, details shape, empty text, error handling, margin logic, real MiniLM accuracy, real latency) |
| `tests/fixtures/jailbreak_semantic.py` | Semantic bypass samples and benign semantic samples |
