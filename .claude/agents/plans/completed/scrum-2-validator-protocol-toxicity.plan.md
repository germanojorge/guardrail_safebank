# Plan: SCRUM-2 — Validator Protocol + Toxicity Validator

## Summary

Introduce the `Validator` Protocol (`guardrails/validators/base.py`) and the first concrete implementation `ToxicValidator` (`guardrails/validators/toxic.py`), refactored from the PoC `guardrails.py:113-129`. The protocol is shaped now to absorb PII (S-02), Jailbreak (S-03), and Compliance (S-04) validators without future churn: optional `score`, optional `context`, `name` property, `latency_ms` field on the result, validator-specific payload lives in `details: dict[str, Any]`. Use `Detoxify("multilingual")` (XLM-RoBERTa, includes PT-BR) instead of the PoC's English-only `"original"` model — this matches the PT-BR-first project and is the single change that decides whether real HateBR fixtures actually score >0.7 on first run. Fail-path fixtures come from HateBR (pre-screened locally so the test passes for the right reason, with row IDs cited per `building-rigorously.md §1`). Detoxify loads once at startup and is injected into the validator (testable, no module-level globals). Threshold lives in `config.yaml` under a uniform `validators.<name>.*` schema that the future factory (S-06) will reuse for all four validators.

## User Story

As an engenheiro do pipeline,
I want a Validator protocol and a refactored toxicity detector,
So that all four validators (toxicity, PII, jailbreak, compliance) follow a consistent interface and the LangGraph pipeline can call them uniformly.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (extracts + refactors PoC; new protocol surface) |
| Complexity | LOW–MEDIUM (mechanical refactor + new protocol; HateBR pre-screen adds ~15 min) |
| Systems Affected | `guardrails/` (new package), `tests/`, `pyproject.toml`, `config.yaml`, `.gitignore`, PoC files (renamed) |
| Jira Issue | SCRUM-2 |
| Blocks | SCRUM-7 (S-06 pipeline), SCRUM-11 (S-10 adversarial suite) |
| Labels | `phase-1`, `validators` |

---

## Decisions baked into this plan (from prior research)

1. **Detoxify model: `multilingual`**, not `original`. English-only model on PT-BR HateBR will under-fire and break the fail-path test.
2. **Protocol extensions beyond Jira-literal spec** — add `name: str`, `latency_ms: float | None`, optional `score: float | None`, optional `context: Mapping[str, Any] | None = None` on `run()`. These cost nothing now and avoid a forced refactor at S-02/S-04.
3. **Fixture sourcing: pre-screen HateBR** — download `HateBR.csv` once locally, score candidates through real `Detoxify("multilingual")`, commit 3 samples that actually score >0.7 with row IDs in `tests/fixtures/hatebr_samples.py`. No CI network calls.
4. **Layered jailbreak (future S-03)** = ONE validator with internal stages — already reflected in the protocol shape (no need for chain abstractions).
5. **`config.yaml` containment**: Verified 2026-05-26 — file was gitignored from day one and **never committed to any ref** (`git ls-files config.yaml` empty; no add-event in `git log --all --remotes --diff-filter=A`). No history rewrite needed. **Anthropic key is NOT being rotated this sprint per user decision**; the key has only ever lived on local disk. Flag rotation as recommended-but-deferred in `LIMITATIONS.md` (created in a later phase): risk surface is local backups / shell history / accidental `git add -A`, not pushed history.

6. **PT-BR toxicity model**: Researched 2026-05-26 — `Detoxify("multilingual")` (XLM-R, Jigsaw multilingual) wins over all PT-native candidates (`dougtrajano/*`, `ruanchaves/bert-base-portuguese-cased-hatebr`, `dehatebert-mono-portugese`) for this use case. Reasons: multi-label taxonomy fits the diagnostic API; license is Apache/MIT (HateBR-trained models are research-only); PT is in Jigsaw training data; alternatives are either binary, license-restricted, stale, or have sociopolitical taxonomies that don't fit B2C banking. Post-MVP Extra: fine-tune BERTimbau-large on OLID-BR.

---

## Patterns to Follow

### Toxicity scoring (refactor target)

```python
# SOURCE: guardrails.py:113-129
def verificar_toxicidade(self, texto: str, threshold: float = 0.7) -> tuple:
    """Verifica se o texto contém conteúdo tóxico."""
    resultados = self.detoxify.predict(texto)
    scores_toxicos = {
        "toxicidade": resultados["toxicity"],
        "toxicidade_severa": resultados["severe_toxicity"],
        "obscenidade": resultados["obscene"],
        "ameaca": resultados["threat"],
        "insulto": resultados["insult"],
    }
    for categoria, score in scores_toxicos.items():
        if score > threshold:
            return True, categoria, score
    return False, None, 0.0
```

**Carry forward:** five sub-categories, max-over-categories aggregation, threshold comparison, English keys in the detoxify result (keep them English in the result `details` for portability — drop the PT-BR translation layer; PT-BR display strings belong at the UI/log formatting layer).

**Drop:** mutating metrics, tuple return, hardcoded `"original"` model.

### Detoxify singleton loading

```python
# SOURCE: guardrails.py:9-12
def __init__(self):
    print("Inicializando guardrails...")
    self.detoxify = Detoxify("original")
    print("✓ Detector de toxicidade carregado")
```

**Pattern:** model loaded at constructor. **Change:** inject `Detoxify("multilingual")` from outside (test seam); replace `print` with structlog later. For SCRUM-2, the validator's `__init__` accepts a pre-loaded model OR loads it itself (default behavior). Tests pass a mock.

### Config loading

```python
# SOURCE: real_chatbot.py:16-17
with open(config_path) as f:
    config = yaml.safe_load(f)
```

**Pattern:** pyyaml + path. Keep this exact shape in SCRUM-2 (factory comes in S-06). For now, `ToxicValidator.__init__` accepts `threshold: float` directly; config-driven instantiation is the caller's job.

### Existing test style (DEPARTING from this)

```python
# SOURCE: test_guardrails.py:4-9
def test_funcionalidade_basica():
    """Testa as funcionalidades básicas dos guardrails."""
    print("\n" + "=" * 60)
    ...
```

The PoC tests are **scripts with print statements**, not pytest. SCRUM-2 establishes the real pytest pattern — proper `assert` statements, fixtures, no prints, runnable via `pytest tests/unit/`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.gitignore` | NO-OP | `config.yaml` already on line 24; verified file was never committed |
| `config.yaml` | UPDATE | Add `validators.toxicity.*` block (local-only file, already gitignored) |
| `pyproject.toml` | UPDATE | Add `pytest` to dev group; add `[tool.pytest.ini_options]` |
| `guardrails.py` | RENAME → `_poc_guardrails.py` | Resolve collision with new `guardrails/` package |
| `real_chatbot.py` | UPDATE | Update import to match renamed PoC module |
| `test_guardrails.py` | UPDATE | Update import to match renamed PoC module |
| `guardrails/__init__.py` | CREATE | Make package importable; empty for now |
| `guardrails/validators/__init__.py` | CREATE | Re-export `ValidatorResult`, `Validator`, `ToxicValidator` |
| `guardrails/validators/base.py` | CREATE | `ValidatorResult` dataclass + `Validator` Protocol |
| `guardrails/validators/toxic.py` | CREATE | `ToxicValidator` implementing the protocol |
| `tests/__init__.py` | CREATE | Empty marker |
| `tests/unit/__init__.py` | CREATE | Empty marker |
| `tests/fixtures/__init__.py` | CREATE | Empty marker |
| `tests/fixtures/hatebr_samples.py` | CREATE | 3 pre-screened HateBR samples with row IDs + citation |
| `tests/unit/test_toxic.py` | CREATE | Happy + fail + protocol type-check |
| `scripts/screen_hatebr.py` | CREATE | One-shot local script to pre-screen HateBR candidates (NOT a test, NOT run in CI) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Resolve `guardrails.py` ↔ `guardrails/` collision

- **Files**: `guardrails.py` → `_poc_guardrails.py`; update imports in `real_chatbot.py:1` and `test_guardrails.py:1`
- **Action**: RENAME + UPDATE
- **Implement**:
  - `git mv guardrails.py _poc_guardrails.py`
  - In `real_chatbot.py`, change `from guardrails import ...` → `from _poc_guardrails import ...`
  - In `test_guardrails.py`, change `from guardrails import ...` → `from _poc_guardrails import ...`
  - Add a one-line docstring at top of `_poc_guardrays.py`: `"""Legacy PoC kept for reference; superseded by guardrails/ package."""`
- **Mirror**: N/A
- **Validate**: `python -c "from _poc_guardrails import EnhancedLLMGuardrails"` succeeds; `python -c "import guardrails"` does NOT yet succeed (package not created until Task 5).

### Task 2: Add pytest to dev deps + configure pytest

- **File**: `pyproject.toml`
- **Action**: UPDATE
- **Implement**:
  - Add `"pytest>=8.0"` to `[dependency-groups].dev`
  - Append:
    ```toml
    [tool.pytest.ini_options]
    testpaths = ["tests"]
    python_files = ["test_*.py"]
    addopts = "-ra -q"
    ```
- **Validate**: `uv sync --group dev` succeeds; `uv run pytest --version` prints pytest version.

### Task 3: Add `validators.toxicity.*` block to `config.yaml`

- **File**: `config.yaml`
- **Action**: UPDATE (local-only file; already gitignored, never tracked)
- **Implement**: append:
  ```yaml
  validators:
    toxicity:
      enabled: true
      threshold: 0.7
      model: "multilingual"          # XLM-RoBERTa, supports PT-BR
      applies_to: [input, output]
  ```
- **Note**: Schema designed for the future factory (S-06). Other validators (`pii`, `jailbreak`, `compliance`) will add sibling blocks in their own stories without churning this one.
- **Validate**: `python -c "import yaml; yaml.safe_load(open('config.yaml'))"` parses without error and the `validators.toxicity.threshold` key resolves to `0.7`.

### Task 4: Create `guardrails/` package scaffold

- **Files**: `guardrails/__init__.py`, `guardrails/validators/__init__.py`
- **Action**: CREATE
- **Implement**: both files empty for now. The `validators/__init__.py` will get explicit re-exports in Task 6.
- **Validate**: `uv run python -c "import guardrails; import guardrails.validators"` succeeds.

### Task 5: Implement `Validator` Protocol + `ValidatorResult`

- **File**: `guardrails/validators/base.py`
- **Action**: CREATE
- **Implement**:
  - Imports: `from __future__ import annotations`, `from dataclasses import dataclass, field`, `from typing import Any, Mapping, Protocol, runtime_checkable`
  - `@dataclass` `ValidatorResult` with fields **in this order**:
    - `passed: bool` (required)
    - `category: str` (required — short family tag like `"toxicity"`)
    - `score: float | None = None` (Optional; toxicity sets it, future PII/compliance may not)
    - `details: dict[str, Any] = field(default_factory=dict)`
    - `latency_ms: float | None = None` (filled by calling node or validator itself)
  - `@runtime_checkable` `class Validator(Protocol):`
    - `name: str` (class or instance attribute — Protocol requires the attribute exist)
    - `def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult: ...`
  - Module docstring explaining:
    - `score` is not comparable across validators (toxicity max-sub-score vs. classifier confidence vs. None) — do not aggregate
    - `details` keys are validator-specific; documented per-class
- **Mirror**: N/A — this establishes the pattern
- **Validate**: `uv run python -c "from guardrails.validators.base import ValidatorResult, Validator; r = ValidatorResult(passed=True, category='x'); assert r.score is None and r.details == {} and r.latency_ms is None"` succeeds.

### Task 6: Implement `ToxicValidator`

- **File**: `guardrails/validators/toxic.py`
- **Action**: CREATE
- **Implement**:
  - Imports: `time`, `from typing import Any, Mapping`, `from detoxify import Detoxify`, `from .base import ValidatorResult, Validator` (the Protocol is structural; explicit import keeps mypy happy)
  - `class ToxicValidator:` (no inheritance — it's a structural Protocol implementer)
    - `name = "toxicity"` (class attribute)
    - `__init__(self, threshold: float = 0.7, model_name: str = "multilingual", model: Detoxify | None = None)` — dependency injection: if `model` is provided, use it; else `Detoxify(model_name)` (lets tests pass a mock without loading the real model)
    - `_CATEGORIES = ("toxicity", "severe_toxicity", "obscene", "threat", "insult")` — keep English keys (portability)
    - `run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult`:
      - `t0 = time.perf_counter()`
      - `scores = self._model.predict(text)` — returns dict
      - Filter to `_CATEGORIES`, find `(top_category, top_score) = max(...)`
      - `passed = top_score < self.threshold`
      - Return `ValidatorResult(passed=passed, category="toxicity", score=float(top_score), details={"subscores": {k: float(scores[k]) for k in self._CATEGORIES}, "top_category": top_category, "threshold": self.threshold, "model": model_name}, latency_ms=(time.perf_counter()-t0)*1000)`
  - Module docstring: list the keys populated in `details`.
- **Mirror**: scoring logic mirrors `guardrails.py:113-129` (5-category, max aggregation, threshold comparison) but returns `ValidatorResult` instead of a tuple and drops metrics side-effects.
- **Validate**: `uv run python -c "from guardrails.validators.toxic import ToxicValidator"` succeeds (does NOT instantiate — that would download the model).

### Task 7: Re-export from `guardrails/validators/__init__.py`

- **File**: `guardrails/validators/__init__.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  from .base import Validator, ValidatorResult
  from .toxic import ToxicValidator

  __all__ = ["Validator", "ValidatorResult", "ToxicValidator"]
  ```
- **Validate**: `uv run python -c "from guardrails.validators import ToxicValidator, Validator, ValidatorResult"` succeeds.

### Task 8: Pre-screen HateBR fixtures (one-shot, local only)

- **File**: `scripts/screen_hatebr.py`
- **Action**: CREATE (will be deleted or kept as a documented one-shot in a follow-up; not run in CI)
- **Implement**: a small script that:
  - Downloads `HateBR.csv` from the GitHub raw URL `https://raw.githubusercontent.com/franciellevargas/HateBR/main/dataset/HateBR.csv` (verify the exact path during execution — if it's renamed, use the closest equivalent)
  - Loads CSV with pandas or csv stdlib
  - Filters rows where `offensiveness_levels == 3` (most-offensive)
  - For each candidate, runs `Detoxify("multilingual").predict(text)` and prints `(row_id, max_subscore, text)` for samples where `max_subscore > 0.75` (small margin above 0.7)
  - Prints a recommendation block of 5–8 candidates with their row IDs
- **Run**: `uv run python scripts/screen_hatebr.py | tee /tmp/hatebr_screen.txt` — manual, one-shot
- **Validate**: Output lists ≥3 candidates with max-subscore >0.75. If <3 candidates clear the bar, **stop and re-check** the model name or download — do not lower the threshold or hand-craft samples (building-rigorously.md §1).

### Task 9: Commit pre-screened HateBR samples to fixtures

- **File**: `tests/fixtures/hatebr_samples.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring citing: source URL, dataset version (v1.0 if confirmable from repo), license (CC BY-NC 4.0), access date (2026-05-26), and the row IDs included
  - Constant `TOXIC_SAMPLES: list[tuple[str, str]]` = list of `(row_id, text)` pairs — pick 3 from screened output that comfortably exceed the threshold
  - Constant `BENIGN_SAMPLES: list[str]` — 3 short PT-BR benign prompts. **These ARE hand-crafted but that's permissible**: the rule applies to fixtures that test the *positive* (catch-the-bad-thing) path; benign-path fixtures can be anything that confidently doesn't trigger.
- **Validate**: `uv run python -c "from tests.fixtures.hatebr_samples import TOXIC_SAMPLES, BENIGN_SAMPLES; assert len(TOXIC_SAMPLES) >= 3 and len(BENIGN_SAMPLES) >= 3"` succeeds.

### Task 10: Write `tests/unit/test_toxic.py`

- **File**: `tests/unit/test_toxic.py`
- **Action**: CREATE
- **Implement** (in this order; each is one test function):
  1. **`test_validator_protocol_runtime_check`** — `isinstance(ToxicValidator(), Validator)` evaluates to `True` (the `@runtime_checkable` Protocol attribute check). This satisfies AC #4 (type-check passes). Use `Mock` for the detoxify model so we don't download anything in this test.
  2. **`test_result_dataclass_shape`** — construct a `ValidatorResult` with required-only fields, assert defaults for `score`, `details`, `latency_ms`.
  3. **`test_benign_input_passes` (happy path)** — use a module-scoped pytest fixture that loads `Detoxify("multilingual")` ONCE (`@pytest.fixture(scope="module")`). For each `BENIGN_SAMPLES` entry, assert `result.passed is True`, `result.category == "toxicity"`, `result.score < 0.7`, `result.latency_ms is not None`.
  4. **`test_toxic_input_blocks` (fail path, parametrized)** — `@pytest.mark.parametrize` over `TOXIC_SAMPLES`. For each, assert `result.passed is False`, `result.score > 0.7`, `"top_category" in result.details`, `result.details["subscores"]["toxicity"] >= 0` (sanity).
- **Performance**: gate the heavy detoxify-loading tests behind `@pytest.mark.slow` if needed; default `pytest` run should be <30s. If model download in CI is undesirable, add `@pytest.mark.skipif(os.environ.get("SKIP_HEAVY_TESTS"), ...)` and document in README.
- **Validate**: `uv run pytest tests/unit/test_toxic.py -v` — all 4 tests pass; AC #1 + #2 + #3 + #4 all satisfied by name.

### Task 11: End-to-end validation

- **Action**: VALIDATE
- **Run**:
  ```
  uv sync --group dev
  uv run ruff check .
  uv run pytest tests/unit/test_toxic.py -v
  ```
- **Expected**: ruff clean, pytest 4 passed, no warnings about untyped Protocol.
- **First-run-green warning** (building-rigorously.md §3): if all 4 pass on the very first run, spend 10 minutes trying to break it before declaring done. Specifically:
  - Try a PT-BR sample from HateBR that's labelled offensiveness=2 (medium) — does it score below 0.7? It should, but verify; otherwise the threshold is too low for our model.
  - Try an English profanity input — does it score >0.9? It should (multilingual covers English fine).
  - If neither holds, the screening was off and the validator isn't actually calibrated.

---

## Validation

```bash
# Sync + tooling
uv sync --group dev

# Lint
uv run ruff check .

# Tests (only unit; integration in later stories)
uv run pytest tests/unit/ -v

# Spot-check imports
uv run python -c "from guardrails.validators import ToxicValidator, Validator, ValidatorResult; print('ok')"

# Confirm config.yaml is untracked
git ls-files config.yaml   # should print nothing after Task 1 commit
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| `Detoxify("multilingual")` doesn't score real HateBR samples >0.7 | Task 9 pre-screens against the actual model; if <3 candidates pass, stop and investigate before writing tests |
| CI machine downloads detoxify multilingual on every run (~500MB, slow) | Use `@pytest.fixture(scope="module")` for one load per test session; consider caching the HF model directory in CI later (S-13 polish story) |
| `runtime_checkable` Protocol only checks attribute presence, not method signatures | Acceptable for AC #4 ("type-check passes") — for stricter checking, run `uv run mypy guardrails/` in S-13. Note this limitation in `base.py` docstring. |
| Renamed PoC (`_poc_guardrails.py`) breaks something we didn't grep for | Task 2 explicitly updates the two known importers (`real_chatbot.py`, `test_guardrails.py`); run `rg "from guardrails import" -t py` after the rename to catch anything missed |
| `config.yaml` still in git history with the API key | User chose not to rotate this sprint. Document in `LIMITATIONS.md` (created in a later phase) under "Known security debt". |
| Fixture file imports break when running pytest from different cwd | Use `tests/` as `testpaths` in pyproject (Task 3) and absolute imports `from tests.fixtures...` — ensures consistent resolution |
| HateBR row IDs unstable across dataset versions | Cite both row ID AND the verbatim text + access date in the fixture file's docstring; if the dataset is re-released, the text remains authoritative |

---

## Acceptance Criteria (from Jira SCRUM-2)

- [ ] Given input benigno, when `ToxicValidator.run()` é chamado, then retorna `ValidatorResult(passed=True, category="toxicity", score<threshold)` — **Task 10.3**
- [ ] Given input tóxico (HateBR sample), when `run()` é chamado, then retorna `ValidatorResult(passed=False, category="toxicity", score>0.7)` — **Task 10.4**
- [ ] Given `pytest tests/unit/test_toxic.py` executado, then 100% dos testes passam com happy path + fail path — **Task 11**
- [ ] Given `Validator` protocol em `base.py`, when outro validator implementa `run(text:str) -> ValidatorResult`, then type-check passa — **Task 10.1** (runtime check) + Task 5 (structural definition)

## Plan-level Done Criteria

- [ ] All 11 tasks completed
- [ ] `uv run pytest tests/unit/ -v` shows 4 passed
- [ ] `uv run ruff check .` clean
- [ ] `config.yaml` remains untracked (verified pre-implementation: never committed)
- [ ] No imports of the old `guardrails` module name in `real_chatbot.py` or `test_guardrails.py`
- [ ] HateBR fixture file cites source, license, and row IDs
- [ ] Adversarial review (10 min) completed per building-rigorously.md §3 — see Task 12 first-run-green warning
