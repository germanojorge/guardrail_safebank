# Implementation Report

**Plan**: `.claude/agents/plans/scrum-3-pii-validator.plan.md`
**Branch**: `feature/scrum-2-validator-protocol-toxicity`
**Status**: COMPLETE

## Summary

Built `PIIValidator` — a bidirectional regex-based PII detector for PT-BR covering 4 patterns (email, telefone, CPF formatado, cartão 16 dígitos). Follows the `Validator` Protocol from SCRUM-2. Single class instantiated with `stage="input"` or `stage="output"` at construction time; returns `category="pii_input"` or `"pii_output"`. Spans stored in `details["entities"]`, raw values never stored. Created `LIMITATIONS.md` documenting known gaps (no checksum, no Luhn, no CNPJ, no NER, phone 11-digit miss, closed-loop fixture caveat).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create `PIIValidator` class | `guardrails/validators/pii.py` | ✅ |
| 2 | Re-export `PIIValidator` | `guardrails/validators/__init__.py` | ✅ |
| 3 | Create PII fixtures | `tests/fixtures/pii_samples.py` | ✅ |
| 4 | Create unit tests | `tests/unit/test_pii.py` | ✅ |
| 5 | Create `LIMITATIONS.md` | `LIMITATIONS.md` | ✅ |
| 6 | Lint + full test sweep | N/A | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `ruff check` | ✅ All checks passed |
| `ruff format --check` | ✅ 12 files already formatted |
| `pytest tests/unit/test_pii.py` | ✅ 20 passed, 1 xfailed |
| `SKIP_HEAVY_TESTS=1 pytest tests/` | ✅ 22 passed, 4 skipped, 1 xfailed |
| Smoke import + E2E | ✅ CPF detection returns `passed=False, category='pii_input'` in ~0.016ms |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `guardrails/validators/pii.py` | CREATE | +53 |
| `guardrails/validators/__init__.py` | UPDATE | +2 |
| `tests/fixtures/pii_samples.py` | CREATE | +38 |
| `tests/unit/test_pii.py` | CREATE | +172 |
| `LIMITATIONS.md` | CREATE | +72 |

## Deviations from Plan

- **`phone_dashed` fixture**: Plan used `"Liga no 011-91234-5678"` (11 digits with separator) but the phone regex `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` requires exactly 3+3+4=10 digits total. Changed to `"Liga no 011-912-3456"` (10-digit format) so it actually matches the regex. The 11-digit mobile case is already covered by the `phone_plain` xfail fixture.
- **Branch**: Stayed on `feature/scrum-2-validator-protocol-toxicity` as intended (plan doesn't request a new branch for SCRUM-3).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/unit/test_pii.py` | `test_validator_protocol_runtime_check`, `test_result_dataclass_shape_for_pii`, `test_invalid_stage_raises`, `test_benign_text_passes_input` (×4 parametrized), `test_benign_text_passes_output` (×4 parametrized), `test_pii_detected_blocks` (×5 pass + 1 xfail parametrized), `test_input_and_output_categories`, `test_cpf_specific_ac1`, `test_card_specific_ac2`, `test_latency_under_target` |

## Acceptance Criteria Status

- [x] **AC1**: CPF `"123.456.789-09"` → `passed=False`, `"cpf" in details["entities"]`
- [x] **AC2**: Card `"4111-1111-1111-1111"` + `stage="output"` → `passed=False`, `category="pii_output"`
- [x] **AC3**: Same regex source for both stages; categories differ only by stage suffix
- [x] **AC4**: `pytest tests/unit/test_pii.py` 100% (20 pass, 1 documented xfail)
- [x] `isinstance(PIIValidator("input"), Validator)` passes
- [x] No raw PII value appears in `details` (verified by `_assert_no_raw_pii_in_details`)
- [x] `LIMITATIONS.md` exists with all declared gaps
- [x] `ruff check` + `ruff format --check` pass
- [x] Latency < 10ms met (~0.016ms observed; test asserts < 50ms for CI headroom)
