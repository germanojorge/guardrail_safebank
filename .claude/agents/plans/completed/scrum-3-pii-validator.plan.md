# Plan: PIIValidator (input + output)

## Summary

Build a regex-based PII detector for PT-BR covering 4 patterns (email, telefone, CPF formatado, cartão 16 dígitos) following the `Validator` Protocol established in SCRUM-2. The validator is bidirectional: a single class, instantiated twice — once per guard node — with `stage="input"` or `stage="output"` baked in at construction time, yielding `category="pii_input"` or `"pii_output"`. Detection-only (no masking in MVP); when any pattern matches, `passed=False`. Spans (`m.span()`) are stored in `details` but raw matched values are NEVER stored or logged, per the security requirement in stories.md.

## User Story

As a sistema de compliance,
I want detectar PII (CPF, cartão, email, telefone) tanto no input do usuário quanto no output do LLM,
So that dados sensíveis não vazem em logs nem em respostas.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `guardrails/validators/` package, tests, LIMITATIONS.md |
| Jira Issue | SCRUM-3 |
| Parent Epic | SCRUM-1 |
| Phase | PRD Phase 1 — Validators Core |

---

## Design Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Stage dispatch | **Constructor param** `stage="input"\|"output"` (Option C) | Stage is wiring-time fact; mirrors ToxicValidator's static `category` shape; no runtime footgun |
| `details` schema | **Types + spans only** (no raw values, no masked previews) | stories.md:64 mandates "Loga só tipo de entidade, NUNCA valor"; spans enable future masking Extra |
| Phone regex | **PoC pattern verbatim** | PRD §7 F-2 pins it; richer DDD/+55 union is Extras work; false-positives go in LIMITATIONS.md |
| CPF/cartão validation | **No checksum, no Luhn** | Explicit non-goal per CLAUDE.md pivot 2026-05-25 |
| Score semantics | **`None`** (rule-based) | Per `base.py:5-6` note, scores aren't cross-comparable; honest is `None` |

---

## Patterns to Follow

### Validator class shape

```python
# SOURCE: guardrails/validators/toxic.py:21-57
class ToxicValidator:
    name = "toxicity"

    _CATEGORIES = ("toxicity", "severe_toxicity", "obscene", "threat", "insult")

    def __init__(
        self,
        threshold: float = 0.7,
        model_name: str = "multilingual",
        model: Detoxify | None = None,
    ) -> None:
        self.threshold = threshold
        ...

    def run(
        self, text: str, context: Mapping[str, Any] | None = None
    ) -> ValidatorResult:
        t0 = time.perf_counter()
        ...
        return ValidatorResult(
            passed=passed,
            category="toxicity",
            score=top_score,
            details={...},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
```

### Package exports

```python
# SOURCE: guardrails/validators/__init__.py:1-4
from .base import Validator, ValidatorResult
from .toxic import ToxicValidator

__all__ = ["Validator", "ValidatorResult", "ToxicValidator"]
```

### Test fixture style

```python
# SOURCE: tests/fixtures/hatebr_samples.py — naming convention
# Tuples of (row_id, text) for parametrize compatibility
TOXIC_SAMPLES = [("row_42", "..."), ...]
BENIGN_SAMPLES = ["...", "..."]
```

### Protocol runtime check + parametrize

```python
# SOURCE: tests/unit/test_toxic.py:54-57, 106-117
def test_validator_protocol_runtime_check():
    validator = ...
    assert isinstance(validator, Validator)

@pytest.mark.parametrize("row_id,text", TOXIC_SAMPLES)
def test_toxic_input_blocks(toxic_validator, row_id, text):
    result = toxic_validator.run(text)
    assert result.passed is False
    ...
```

### ValidatorResult dataclass contract

```python
# SOURCE: guardrails/validators/base.py:18-24
@dataclass
class ValidatorResult:
    passed: bool
    category: str
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/validators/pii.py` | CREATE | The `PIIValidator` class |
| `guardrails/validators/__init__.py` | UPDATE | Re-export `PIIValidator` |
| `tests/fixtures/pii_samples.py` | CREATE | Hand-crafted PT-BR samples (4 PII categories + benign) |
| `tests/unit/test_pii.py` | CREATE | Unit tests covering all ACs |
| `LIMITATIONS.md` | CREATE | Declare regex limits + closed-loop fixture caveat |

---

## Regex Patterns (verbatim from PRD §7 F-2 / PoC commit 137af04)

```python
PII_PATTERNS: dict[str, str] = {
    "email":   r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "telefone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    "cpf":      r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "cartao":   r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
}
```

Compile once in `__init__` with `re.compile`. Do not recompile per call.

---

## `details` Schema (locked)

```python
details = {
    "entities": {
        "cpf": [(7, 21)],          # list of (start, end) spans only
        "email": [(33, 52), ...],   # multiple matches per type allowed
    },
    "stage": "input",               # echoes constructor param
    "patterns_checked": ["email", "telefone", "cpf", "cartao"],
}
```

**Forbidden in `details`**: raw matched substrings, hashed values, masked previews. Spans only.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `PIIValidator`

- **File**: `guardrails/validators/pii.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring listing `details` keys (mirror `toxic.py:1-9`)
  - Class-level constant `PII_PATTERNS` dict (4 patterns above) as raw strings
  - Class `PIIValidator` with `name = "pii"`
  - `__init__(self, stage: str = "input") -> None`:
    - Assert `stage in {"input", "output"}` (raise `ValueError` with clear message otherwise)
    - Store `self.stage`
    - Compile patterns once: `self._compiled = {k: re.compile(v) for k, v in PII_PATTERNS.items()}`
  - `run(self, text, context=None) -> ValidatorResult`:
    - `t0 = time.perf_counter()`
    - Iterate patterns; collect `{entity_type: [m.span() for m in pattern.finditer(text)]}`, omit empty entries
    - `passed = not entities` (empty dict → True)
    - Return `ValidatorResult(passed=passed, category=f"pii_{self.stage}", score=None, details={"entities": entities, "stage": self.stage, "patterns_checked": list(PII_PATTERNS.keys())}, latency_ms=(time.perf_counter()-t0)*1000)`
- **Mirror**: `guardrails/validators/toxic.py:1-57`
- **Validate**: `uv run python -c "from guardrails.validators import pii"` (no import errors)

### Task 2: Re-export `PIIValidator`

- **File**: `guardrails/validators/__init__.py`
- **Action**: UPDATE
- **Implement**: Add `from .pii import PIIValidator` and append `"PIIValidator"` to `__all__`
- **Mirror**: `guardrails/validators/__init__.py:1-4`
- **Validate**: `uv run python -c "from guardrails.validators import PIIValidator"`

### Task 3: Create PII fixtures

- **File**: `tests/fixtures/pii_samples.py`
- **Action**: CREATE
- **Implement**:
  - `BENIGN_SAMPLES: list[str]` — 3–4 PT-BR strings with NO PII (e.g., "Qual é o limite do cartão Gold?", "Meu cartão foi bloqueado, como desbloqueio?", "Quero saber sobre o programa de pontos")
  - `PII_SAMPLES: list[tuple[str, str, str]]` — tuples of `(case_id, expected_entity_type, text)`, e.g.:
    - `("cpf_formatted", "cpf", "Meu CPF é 123.456.789-09 para cadastro.")`
    - `("card_dashed", "cartao", "Meu cartão é 4111-1111-1111-1111, pode confirmar?")`
    - `("card_spaced", "cartao", "Cartão 4111 1111 1111 1111")`
    - `("email_simple", "email", "Mande para joao.silva@example.com.br")`
    - `("phone_dashed", "telefone", "Liga no 011-91234-5678")`
    - `("phone_plain", "telefone", "Meu fone é 11912345678")` — *may xfail; document if so*
  - Module docstring declaring: "Hand-crafted fixtures — closed-loop risk per building-rigorously.md §1. External corpus not available for PT-BR PII at MVP scope; see LIMITATIONS.md."
- **Mirror**: `tests/fixtures/hatebr_samples.py` (tuple shape + module docstring style)
- **Validate**: `uv run python -c "from tests.fixtures.pii_samples import PII_SAMPLES, BENIGN_SAMPLES"`

### Task 4: Create unit tests

- **File**: `tests/unit/test_pii.py`
- **Action**: CREATE
- **Implement**:
  - `test_validator_protocol_runtime_check` — `isinstance(PIIValidator("input"), Validator)` (AC4 protocol part)
  - `test_result_dataclass_shape_for_pii` — sanity check on `ValidatorResult` returned by an empty-text call (or benign)
  - `test_invalid_stage_raises` — `PIIValidator("middle")` raises `ValueError`
  - `test_benign_text_passes` — parametrize over `BENIGN_SAMPLES`; both `stage="input"` and `stage="output"` instances; asserts `passed=True`, `category="pii_input"` or `"pii_output"`, `details["entities"] == {}`, `latency_ms is not None`
  - `test_pii_detected_blocks` — parametrize over `PII_SAMPLES`; asserts:
    - `result.passed is False`
    - `result.category == "pii_input"` (instance under test is `stage="input"`)
    - `expected_entity_type in result.details["entities"]`
    - Spans are tuples of two ints
    - **NO raw match value appears anywhere in `result.details`** (assert by checking each string in `details["entities"].keys()` is one of the 4 entity types, and recursive scan that no value contains the original CPF/email/etc. substring)
  - `test_input_and_output_categories` — instantiate `PIIValidator("input")` and `PIIValidator("output")`; feed both the same CPF string; assert categories differ but `details["entities"]` matches (AC2 + AC3 — same regex source of truth)
  - `test_cpf_specific_ac1` — exact AC1 phrasing: text `"Meu CPF é 123.456.789-09"`; assert `passed=False` and `"cpf" in details["entities"]`
  - `test_card_specific_ac2` — exact AC2 phrasing: `"4111-1111-1111-1111"` with `stage="output"` instance; assert `passed=False` and `category=="pii_output"`
  - `test_latency_under_target` — sanity: latency < 50ms on a 1KB input (target is <10ms; loose bound for CI variance)
- **Mirror**: `tests/unit/test_toxic.py:50-117`
- **Validate**: `uv run pytest tests/unit/test_pii.py -v`

### Task 5: Create `LIMITATIONS.md`

- **File**: `LIMITATIONS.md` (repo root)
- **Action**: CREATE
- **Implement**: Markdown sections:
  - **PII validator**:
    - No CPF checksum — accepts mathematically invalid CPFs like `000.000.000-00` and `123.456.789-00`
    - No Luhn validation — accepts invalid card numbers like `1111-1111-1111-1111`
    - No CNPJ, no conta bancária, no nome/endereço (NER)
    - Phone regex matches 10-digit sequences only; misses `(11) 91234-5678`, `+55 11 91234-5678`, and unformatted 11-digit mobile numbers. Also produces false positives against dates and CPF tails.
    - Email regex is RFC-naive; will under-match unicode TLDs and over-match in code blocks
    - Hand-crafted fixtures = closed validation loop (building-rigorously.md §1); no external PT-BR PII corpus at MVP scope
  - **Roadmap (Extras)**: Presidio Analyzer + CPF/CNPJ checksum + Luhn (cited from CLAUDE.md Extras table)
- **Mirror**: `CLAUDE.md` markdown style; sections per validator so jailbreak/compliance can append later
- **Validate**: `cat LIMITATIONS.md | head -30` shows content; markdown renders cleanly

### Task 6: Lint + full test sweep

- **File**: N/A (validation only)
- **Action**: VALIDATE
- **Implement**: Run the full validation block below
- **Validate**: All green

---

## Validation

```bash
# Lint
uv run ruff check guardrails/ tests/
uv run ruff format --check guardrails/ tests/

# Tests (fast subset — no Detoxify model load needed for PII)
uv run pytest tests/unit/test_pii.py -v

# Full suite (will load Detoxify unless SKIP_HEAVY_TESTS=1)
SKIP_HEAVY_TESTS=1 uv run pytest tests/ -v

# Smoke import check
uv run python -c "from guardrails.validators import PIIValidator; v = PIIValidator('input'); print(v.run('Meu CPF é 123.456.789-09'))"
```

---

## Acceptance Criteria

Mapped 1:1 to Jira SCRUM-3:

- [ ] **AC1**: Given `"Meu CPF é 123.456.789-09"`, `PIIValidator("input").run()` returns `passed=False` with `"cpf" in details["entities"]` → `test_cpf_specific_ac1`
- [ ] **AC2**: Given `"4111-1111-1111-1111"` and `stage="output"`, returns `passed=False` with `category="pii_output"` → `test_card_specific_ac2`
- [ ] **AC3**: Same regex source for both stages; categories differ only by stage suffix → `test_input_and_output_categories`
- [ ] **AC4**: `pytest tests/unit/test_pii.py` 100% passes covering 4 regex patterns → all parametrized tests green
- [ ] Plus: `isinstance(PIIValidator("input"), Validator)` runtime check passes
- [ ] Plus: no raw PII string appears anywhere in `details` (security req from stories.md:64)
- [ ] Plus: `LIMITATIONS.md` exists declaring no checksum, no Luhn, no CNPJ, no NER, closed-loop fixture caveat
- [ ] Plus: `ruff check` + `ruff format --check` pass
- [ ] Plus: Latency budget `<10ms` met for representative inputs (loose assertion at 50ms in tests)

---

## Risks

| Risk | Mitigation |
|------|------------|
| Card regex over-matches any 16-digit numeric sequence (e.g., loyalty IDs, tracking codes) | Document in `LIMITATIONS.md`; future Luhn validation is Extras |
| Phone regex over-matches CPF tails (`789-1234` segment) and dates | Document in `LIMITATIONS.md`; pattern order doesn't matter since we collect all matches independently |
| Closed-loop fixtures: same person wrote regex + samples | Explicitly declared in fixtures module docstring + `LIMITATIONS.md` per building-rigorously.md §1; AC4 only requires pattern coverage, not adversarial breadth |
| Forgetting `assert` on raw-value-leak in `details` would silently violate security req | Dedicated assertion in `test_pii_detected_blocks` scans `details` for any original input substring |
| ToxicValidator pattern uses `model_name` constructor arg; PIIValidator has no analogous concept — risk of accidental over-design | Keep `__init__` to `stage` only. Defer custom patterns parameter to a future story if needed |
| `re.compile` raising on bad pattern at import time | Patterns are static + tested; failure surfaces immediately in import smoke check (Task 1 validate) |

---

## Out of Scope (defer to Extras / future stories)

- PII masking (current MVP blocks; masking is in Extras table of CLAUDE.md)
- Presidio integration
- CPF/CNPJ checksum, Luhn for cards
- NER for names/addresses
- Custom user-supplied patterns
- LangGraph integration (separate story, SCRUM-? Phase 2)

---

## Next Step

Review the plan, then run `/implement .claude/agents/plans/scrum-3-pii-validator.plan.md` to execute the 6 tasks in order.
