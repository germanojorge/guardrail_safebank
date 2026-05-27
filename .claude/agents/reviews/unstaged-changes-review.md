# Code Review: Unstaged Changes

**Scope**: Unstaged working-tree changes (rename project + PII regex/NER hardening)
**Recommendation**: NEEDS WORK (minor cleanup + test debt)

## Summary

Reviewed 10 modified files. The bulk of the diff is a project-wide rename (`llm-guardrails-tutorial` → `guardrail-safebank`) plus two meaningful code changes in the PII validator:

1. **Telephone regex expanded** to catch more PT-BR formats (DDD with leading zero, 3–5 digit prefixes).
2. **Presidio NER layer hardened** with a min-score gate (0.85), a large deny-list of banking/common terms, and restriction to `stage="input"` only.

Both changes fix real test failures that existed on `main` before this diff (3 PII unit-test failures → 0). The rename is consistent and mechanically correct across Docker, TOML, and docs.

---

## Issues Found

### Critical
None.

### High Priority
1. **Pre-existing API test breakage** — `tests/api/conftest.py::_build_mock_components` returns a 7-tuple but `guardrails/api/app.py` unpacks 8 values (`graph, toxic, pii_input, jailbreak, compliance, llm, embedding, vector_store`). This causes **all** API tests to fail with `ValueError: not enough values to unpack`.  
  *Impact*: CI is red regardless of this diff.  
  *Fix*: Add `mock_pii_input` and `mock_pii_output` to the returned tuple in `_build_mock_components`, or return a dict/namespace to avoid positional drift.

### Medium Priority
2. **XPASS on two xfail-marked PII cases** — `phone_plain` (unformatted mobile `11912345678`) and `cpf_unformatted` (plain 11 digits `12345678909`) now pass thanks to the improved regex. The `@pytest.mark.xfail` annotations in `tests/unit/test_pii.py` should be removed so the suite stays green without surprises.  
  *Fix*: Remove the `xfail` markers for these two parametrized cases.

3. **Missing unit tests for new Presidio logic** — The diff adds `_PRESIDIO_MIN_SCORE`, `_PRESIDIO_DENYLIST`, and the `stage == "input"` branch guard, but there are no explicit tests for:
   - A term on the deny-list being ignored despite a high Presidio score.
   - A score below 0.85 being ignored.
   - `stage="output"` skipping Presidio entirely even if the engine is present.
   *Fix*: Add 2–3 fast unit tests that inject a mock `AnalyzerEngine` (or monkeypatch `analyze`) to exercise each branch.

4. **Telephone regex potential over-capture** — The new pattern `0?\d{2}[\s\-]\d{3,5}[\s\-]?\d{4}` will match any 10-digit sequence formatted as `DDD prefix suffix` even when the prefix does **not** start with `9` (i.e. fixed-line numbers). That is acceptable for a banking guardrail (fixed lines are also PII), but it is a broader surface than the old regex which required 4–5 digit prefix. Document the intent in `LIMITATIONS.md` if fixed-line support was not previously claimed.

### Low Priority
5. **Deny-list hygiene** — The word `"cada"` appears twice in `_PRESIDIO_DENYLIST`. Duplicate entries in a `set` are harmless but suggest the list was copy-pasted without review.  
  *Fix*: De-duplicate and sort the set for maintainability.

6. **Regex comment drift** — The comment block above the `telefone` pattern in `_pii_patterns.py` still says:
   > "Requires explicit separator (space or dash) after DDD to avoid matching substrings of CPF or card numbers."
   The new regex also allows `0?` before the DDD, but the comment was not updated to mention the leading-zero case (`011`).  
   *Fix*: Update the inline docstring to mention `0?\d{2}` (e.g. `011`).

---

## Validation Results

| Check | Status |
|-------|--------|
| Syntax (`py_compile`) | PASS |
| Lint (ruff) | PASS |
| Unit tests (`tests/unit/test_pii.py`) | PASS (0 failures; 1 expected XFAIL) |
| API tests (`tests/api/`) | FAIL — pre-existing `conftest.py` tuple-length mismatch (see H1) |

### Test delta before vs after this diff
- **Baseline** (`main` without these changes): 3 PII unit-test failures (Presidio false-positive on "programa de pontos" + missed `011-912-3456`).
- **With diff**: 0 PII unit-test failures. The diff successfully fixes the reported issues.

---

## What's Good

- **The deny-list approach is pragmatic** — spaCy `pt_core_news_sm` is indeed noisy (~40 % FP on banking text); a block-list is the right short-term mitigation given the MVP deadline.
- **Stage-gating Presidio** (`stage == "input"`) is a smart latency/precision trade-off: output guard still catches critical PII via regex while avoiding NER hallucinations on LLM-generated prose.
- **Consistent rename** — every occurrence of the old project name in Docker, TOML, PRD, and settings was updated; nothing was left dangling.
- **Checksum layer untouched** — CPF/CNPJ/Luhn validators remain deterministic and fast, which is correct.

---

## Recommendation

1. **Before merging**: Remove the two stale `xfail` markers in `tests/unit/test_pii.py`.
2. **Before merging**: De-duplicate `"cada"` in `_PRESIDIO_DENYLIST` and update the `telefone` regex comment.
3. **Next PR** (or same PR if time permits): Fix `_build_mock_components` in `tests/api/conftest.py` so API tests can run again. Consider returning a small dataclass instead of a bare tuple to prevent future positional skew when new validators are added.
4. **Next PR**: Add explicit unit tests for the Presidio min-score, deny-list, and stage-gating logic.

Overall the PII changes are **correct, well-scoped, and improve test health**. Approve once the `xfail` cleanup and minor comment fixes are applied.
