# Implementation Report

**Plan**: `.claude/agents/plans/completed/scrum-2-validator-protocol-toxicity.plan.md`
**Branch**: `feature/scrum-2-validator-protocol-toxicity`
**Status**: COMPLETE

## Summary

Introduced the `Validator` Protocol (`guardrails/validators/base.py`) and the first concrete implementation `ToxicValidator` (`guardrails/validators/toxic.py`), refactored from `_poc_guardrails.py`. Added pytest to dev deps, configured pytest in `pyproject.toml`, scaffolded the `tests/` directory with pre-screened HateBR fixtures, and wrote 6 unit tests (all passing).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Rename guardrails.py → _poc_guardrails.py + update imports | `_poc_guardrails.py`, `real_chatbot.py`, `test_guardrails.py` | ✅ |
| 2 | Add pytest to dev deps + configure pytest | `pyproject.toml` | ✅ |
| 3 | Add validators.toxicity block to config.yaml | `config.yaml` (untracked) | ✅ |
| 4 | Create guardrails/ package scaffold | `guardrails/__init__.py`, `guardrails/validators/__init__.py` | ✅ |
| 5 | Implement Validator Protocol + ValidatorResult | `guardrails/validators/base.py` | ✅ |
| 6 | Implement ToxicValidator | `guardrails/validators/toxic.py` | ✅ |
| 7 | Re-export from validators __init__.py | `guardrails/validators/__init__.py` | ✅ |
| 8 | Create screen_hatebr.py script | `scripts/screen_hatebr.py` | ✅ |
| 9 | Commit pre-screened HateBR samples to fixtures | `tests/fixtures/hatebr_samples.py` | ✅ |
| 10 | Write tests/unit/test_toxic.py | `tests/unit/test_toxic.py` | ✅ |
| 11 | End-to-end validation | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| ruff check | ✅ |
| pytest tests/unit/test_toxic.py | ✅ 6 passed in 12.3s |
| Import spot-check | ✅ |
| config.yaml untracked | ✅ |

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `guardrails.py` | RENAME → `_poc_guardrails.py` | Added PoC docstring |
| `real_chatbot.py` | UPDATE | Import updated to `_poc_guardrails` |
| `test_guardrails.py` | UPDATE | Import updated to `_poc_guardrails` |
| `pyproject.toml` | UPDATE | pytest>=8.0, pytest config, slow mark |
| `config.yaml` | UPDATE | Added validators.toxicity block (untracked) |
| `guardrails/__init__.py` | CREATE | Empty package marker |
| `guardrails/validators/__init__.py` | CREATE | Re-exports Validator, ValidatorResult, ToxicValidator |
| `guardrails/validators/base.py` | CREATE | +34 lines |
| `guardrails/validators/toxic.py` | CREATE | +52 lines |
| `tests/__init__.py` | CREATE | Empty marker |
| `tests/fixtures/__init__.py` | CREATE | Empty marker |
| `tests/unit/__init__.py` | CREATE | Empty marker |
| `tests/fixtures/hatebr_samples.py` | CREATE | +44 lines |
| `tests/unit/test_toxic.py` | CREATE | +109 lines |
| `scripts/screen_hatebr.py` | CREATE | +68 lines |

## Deviations from Plan

1. **HateBR CSV column names differ from plan**: Plan assumed `offensiveness_levels==3` and `instagram_comments` columns. HateBR v1.0 actual columns are `label_final` (binary 0/1) and `comentario`. Corrected in `scripts/screen_hatebr.py` and documented in `tests/fixtures/hatebr_samples.py` docstring.

2. **6 tests collected instead of 4**: `@pytest.mark.parametrize` over 3 TOXIC_SAMPLES expands test_toxic_input_blocks into 3 parametrized cases → 2 + 1 + 3 = 6 total tests. Expected "4 tests" in plan was based on counting test functions, not parametrized expansions. All 6 pass.

3. **`slow` mark registered in pyproject.toml**: Added `markers` to `[tool.pytest.ini_options]` to suppress PytestUnknownMarkWarning — not in plan but a trivial quality fix.

## Adversarial Review Findings (building-rigorously.md §3)

| Input | Score | Pass/Block | Assessment |
|-------|-------|------------|------------|
| Moderate political criticism PT-BR ("péssimo e incompetente") | 0.9949 | Block | Model is aggressive on PT-BR political language — known limitation of Jigsaw multilingual. Acceptable for banking context (conservative is better than permissive). |
| English profanity ("stupid idiot, f*** yourself") | 0.9982 | Block ✅ | Multilingual handles English fine |
| Indirect insult PT-BR ("péssimo caráter, tão desonesto") | 0.8714 | Block | Correct — this IS an insult |
| Negation bypass ("não é um idiota") | 0.4792 | Pass ✅ | Negation handled correctly |

**Key finding**: False positive risk on heated-but-legitimate political discourse (score 0.99 on "terrible and incompetent"). For B2C banking, this is an acceptable trade-off given the demo context. Document in LIMITATIONS.md (to be created in a later story).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/unit/test_toxic.py` | test_validator_protocol_runtime_check, test_result_dataclass_shape, test_benign_input_passes, test_toxic_input_blocks[2366], test_toxic_input_blocks[1712], test_toxic_input_blocks[266] |
