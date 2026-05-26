# Plan: SCRUM-10 — Adversarial Test Suite from External Sources

## Summary

Build a `tests/adversarial/` integration tier that runs the **full pipeline** against fixtures sourced from **external** datasets (JailbreakBench, HateBR, RealToxicityPrompts) plus hand-crafted PT-BR adversarial prompts. The suite produces concrete block-rate metrics (substring-only vs substring+DeBERTa) that populate the "TBD" cells in `LIMITATIONS.md` and back the interview narrative against the closed-validation-loop failure mode (`building-rigorously.md §1`). A one-shot translation script (`scripts/translate_fixtures.py`) uses Claude to render EN JailbreakBench paraphrases into PT-BR. JSONL is the carrier for ingested/translated data; Python fixtures stay for hand-crafted samples (current convention preserved).

Also includes the **carry-over** `09_produtos_investimento.md` banking KB doc that baits the LLM into a Compliance R2 violation for demo Beat 4.

## User Story

As an engineer of rigor (`building-rigorously.md §1`),
I want adversarial fixtures sourced from external authors — distinct from the matcher author —
So that the reported block rate is not a tautological measure, and the interview narrative has hard numbers behind the layered-defense claim.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `tests/adversarial/` · `scripts/` · `LIMITATIONS.md` · `pyproject.toml` · `data/banking_kb/` · `guardrails/validators/jailbreak.py` |
| Jira Issue | SCRUM-10 |

---

## Key Decisions (decided up-front)

1. **File format split**: `.jsonl` for **ingested/translated** external data (`jailbreak_external.jsonl`, `toxic_external.jsonl`); existing `.py` fixtures stay for hand-crafted samples (PII, Compliance). Each JSONL line: `{"id": str, "text": str, "lang": "pt-br|en", "source": "jailbreakbench|hatebr|realtoxicityprompts", "expected": "block|allow"}`.
2. **Test directory**: `tests/adversarial/` (new), separate from `tests/unit/`. Uses `@pytest.mark.adversarial` marker so CI can run the offline subset and skip the network-heavy compliance suite.
3. **Compliance suite scope**: keep hand-crafted (the Claude judge IS the matcher; external compliance datasets don't exist for PT-BR banking). Declare closed-loop explicitly in `LIMITATIONS.md` and add `@pytest.mark.network` to skip in offline CI.
4. **Translation strategy**: one-shot `scripts/translate_fixtures.py` reads source JSONL with EN prompts, calls Claude via `AnthropicProvider.complete()`, writes PT-BR JSONL. Manual review checklist embedded in the output file.
5. **Block-rate threshold**: ≥80% on JailbreakBench PT-BR; ≥80% on HateBR + RealToxicityPrompts mix. If first run is below threshold, **do not lower it** — investigate and document gaps per `building-rigorously.md §3`. Threshold is a failing condition, not aspirational.
6. **Metrics script**: `scripts/measure_jailbreak_layers.py` — runs each sample through (a) substring-only (disable DeBERTa via constructor arg), (b) full pipeline. Outputs a markdown table appended to `LIMITATIONS.md` between fence markers.
7. **JailbreakBench license**: MIT. Cite source + access date in JSONL header.
8. **RealToxicityPrompts license**: CC-BY 4.0. Cite source.

---

## Patterns to Follow

### Validator structure — injection pattern

```python
# SOURCE: guardrails/validators/toxic.py:21-57
# Constructor accepts optional injected dependency (None = load real model)
class ToxicValidator:
    name = "toxicity"

    def __init__(self, threshold=0.7, model_name="multilingual", model=None):
        self._model = model if model is not None else Detoxify(model_name)

    def run(self, text, context=None) -> ValidatorResult:
        ...
        return ValidatorResult(passed=passed, category="toxicity", ...)
```

### Pipeline build_graph — injection pattern

```python
# SOURCE: guardrails/pipeline/graph.py:21-107
# build_graph() accepts all validators/providers as optional args
# Every arg defaults to a real instance — inject mocks in tests
graph = build_graph(
    toxic=..., pii_input=..., pii_output=..., jailbreak=...,
    compliance=..., llm_provider=..., embedding=..., vector_store=...,
)
result = graph.invoke({"message": text, "diagnostics": {}})
assert result["blocked"] is True
```

### Fixture file structure — group by detection layer

```python
# SOURCE: tests/fixtures/jailbreak_samples.py:1-93
SUBSTRING_CAUGHT_SAMPLES: list[tuple[str, str]] = [("id", "text"), ...]
DEBERTA_ONLY_SAMPLES: list[tuple[str, str]] = [("id", "text"), ...]
KNOWN_BYPASSES = [pytest.param("id", "text", marks=pytest.mark.xfail(...)), ...]
BENIGN_SAMPLES: list[str] = ["text", ...]
```

### External-screening one-shot scripts

```python
# SOURCE: scripts/screen_hatebr.py:1-60
# - Live download (urllib), filter by source-specific label, score through Detoxify,
#   print candidates above threshold. NOT in CI. Human curates output → fixture file.
HATEBR_URL = "https://raw.githubusercontent.com/.../HateBR.csv"
SCORE_THRESHOLD = 0.75
```

### Test markers — slow / adversarial / network gating

```toml
# SOURCE: pyproject.toml:44-46
markers = [
    "slow: marks tests that load heavy ML models (deselect with -m 'not slow')",
]
# ADD:
markers = [
    "slow: ...",
    "adversarial: marks adversarial integration tests (external fixtures, full pipeline)",
    "network: marks tests that require external API calls (Anthropic, HF datasets download)",
]
```

### Parametrized test pattern with sample_id labels

```python
# SOURCE: tests/unit/test_jailbreak.py (parametrized fixture loop)
@pytest.mark.parametrize("sample_id,text", SUBSTRING_CAUGHT_SAMPLES)
def test_substring_layer(sample_id, text):
    result = validator.run(text)
    assert result.passed is False
    assert result.details["layer_caught"] == "substring"
```

### Limitation declarations — table per validator

```markdown
# SOURCE: LIMITATIONS.md:30-39
### Layered-defense comparison (jailbreak)
| Layer | SUBSTRING_CAUGHT_SAMPLES | DEBERTA_ONLY_SAMPLES |
| Substring only | 3/3 (100%) | 0/3 (0%) |
| Substring + DeBERTa | 3/3 (100%) | TBD |
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `data/banking_kb/09_produtos_investimento.md` | CREATE | Beat 4 carry-over: doc baits LLM into recommending CDB Premium → triggers R2 |
| `pyproject.toml` | UPDATE | Add `adversarial` and `network` pytest markers |
| `guardrails/validators/jailbreak.py` | UPDATE | Constructor flag `use_deberta: bool = True` for metrics script |
| `tests/adversarial/__init__.py` | CREATE | Package marker |
| `tests/adversarial/conftest.py` | CREATE | JSONL loader fixture + full-pipeline graph fixture |
| `tests/adversarial/fixtures/__init__.py` | CREATE | Package marker |
| `tests/adversarial/fixtures/jailbreak_external.jsonl` | CREATE | 20-30 prompts (10-15 EN JBB + 10-15 PT-BR translations) |
| `tests/adversarial/fixtures/toxic_external.jsonl` | CREATE | 20-30 prompts (HateBR PT-BR + RealToxicityPrompts EN) |
| `tests/adversarial/fixtures/pii_handcrafted.jsonl` | CREATE | 15-20 hand-crafted PT-BR with `closed_loop: true` flag |
| `tests/adversarial/fixtures/compliance_handcrafted.jsonl` | CREATE | 15-20 hand-crafted with closed-loop flag |
| `tests/adversarial/test_jailbreak_pipeline.py` | CREATE | Full pipeline; assert block rate ≥80% on external prompts |
| `tests/adversarial/test_toxic_pipeline.py` | CREATE | Same shape; HateBR + RTP |
| `tests/adversarial/test_pii_pipeline.py` | CREATE | Hand-crafted only; pure pipeline tests |
| `tests/adversarial/test_compliance_pipeline.py` | CREATE | `@pytest.mark.network` — calls real Claude Haiku judge |
| `scripts/screen_realtoxicityprompts.py` | CREATE | One-shot pre-screen: download RTP, filter top toxic prompts |
| `scripts/translate_fixtures.py` | CREATE | One-shot: EN JBB prompts → PT-BR via Claude, write to JSONL |
| `scripts/measure_jailbreak_layers.py` | CREATE | Substring-only vs substring+DeBERTa block-rate table |
| `LIMITATIONS.md` | UPDATE | Fill in "TBD" cells; add fenced markers; declare closed-loop for PII + Compliance JSONL |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Investments doc for Beat 4 (SCRUM-10 carry-over)

- **File**: `data/banking_kb/09_produtos_investimento.md`
- **Action**: CREATE
- **Implement**: hand-write a doc named "Produtos de Investimento" listing CDB Premium with a `rendimento garantido` framing that, when surfaced by RAG and used by the LLM in a generic "investir 10 mil reais" answer, baits the LLM into recommending a specific product (Compliance R2 violation). Keep the doc itself NOT violating R2 — only the LLM's reformulation does. ~250 words.
- **Mirror**: `data/banking_kb/02_cdb.md` for structure
- **Validate**: `uv run python scripts/ingest_banking_kb.py` succeeds; semantic search `"investir 10 mil reais"` returns the new doc in top-3

### Task 1: Add pytest markers

- **File**: `pyproject.toml`
- **Action**: UPDATE
- **Implement**: add `adversarial` and `network` markers under `[tool.pytest.ini_options].markers`. Default `addopts` stays the same.
- **Validate**: `uv run pytest --markers | grep -E "adversarial|network"`

### Task 2: JailbreakValidator — `use_deberta` flag

- **File**: `guardrails/validators/jailbreak.py`
- **Action**: UPDATE
- **Implement**: add `use_deberta: bool = True` to `__init__`. When `False`, `run()` returns the substring-layer result without invoking DeBERTa. No other behavior changes.
- **Mirror**: existing constructor pattern at `guardrails/validators/jailbreak.py:53-69`
- **Validate**: `uv run pytest tests/unit/test_jailbreak.py -q` (all pass) + add one new test asserting `use_deberta=False` skips the pipeline call

### Task 3: Pre-screen RealToxicityPrompts

- **File**: `scripts/screen_realtoxicityprompts.py`
- **Action**: CREATE
- **Implement**: download a public toxic-prompt subset (HuggingFace `allenai/real-toxicity-prompts`, "challenging" split), score through Detoxify, print top-20 with `max_subscore > 0.75`. Run manually — output curated into Task 5 fixture.
- **Mirror**: `scripts/screen_hatebr.py:1-60`
- **Validate**: `uv run python scripts/screen_realtoxicityprompts.py` prints ≥15 candidates

### Task 4: Translate JailbreakBench EN → PT-BR

- **File**: `scripts/translate_fixtures.py`
- **Action**: CREATE
- **Implement**: read `tests/fixtures/jailbreak_samples.py:DEBERTA_ONLY_SAMPLES` (EN paraphrases), call `AnthropicProvider.complete()` with a translation prompt that preserves adversarial intent, write JSONL with `lang: "pt-br"`, `source: "jailbreakbench-translated"`, `expected: "block"`. Idempotent: skip if output exists; `--force` flag.
- **Mirror**: `scripts/ingest_banking_kb.py` for argv/idempotency pattern
- **Validate**: `ANTHROPIC_API_KEY=... uv run python scripts/translate_fixtures.py`; output JSONL has ≥10 PT-BR lines

### Task 5: Create toxic external JSONL fixture

- **File**: `tests/adversarial/fixtures/toxic_external.jsonl`
- **Action**: CREATE
- **Implement**: 20-30 lines. ~12 from HateBR PT-BR (from existing `hatebr_samples.py`, re-encoded as JSONL), ~10 from Task 3 output (RealToxicityPrompts EN). Schema: `{"id", "text", "lang", "source", "expected": "block"}`. First line is a `#` comment-header citing sources, licenses, access date.
- **Validate**: `wc -l tests/adversarial/fixtures/toxic_external.jsonl` ≥ 21

### Task 6: Create jailbreak external JSONL fixture

- **File**: `tests/adversarial/fixtures/jailbreak_external.jsonl`
- **Action**: CREATE
- **Implement**: merge EN JBB samples (from existing `DEBERTA_ONLY_SAMPLES`) + PT-BR translations from Task 4 into a single JSONL. Schema: `{"id", "text", "lang", "source", "technique": "persona|fiction|hypothetical|...", "expected": "block"}`. Header line cites JailbreakBench (MIT) + access date.
- **Validate**: `wc -l` ≥ 21; `jq -s '[.[] | select(.lang=="pt-br")] | length'` ≥ 10

### Task 7: Create hand-crafted PII + Compliance JSONL fixtures

- **Files**:
  - `tests/adversarial/fixtures/pii_handcrafted.jsonl`
  - `tests/adversarial/fixtures/compliance_handcrafted.jsonl`
- **Action**: CREATE
- **Implement**: 15-20 lines each. Header line MUST include `"closed_loop": true` flag and a one-line rationale. PII covers email/telefone/cpf/cartao variations including the xfail formats from `LIMITATIONS.md` (so adversarial suite agrees with existing limits). Compliance covers R1-R5 with at least one **subtle** case per rule.
- **Validate**: `wc -l` ≥ 16 each

### Task 8: Create adversarial conftest — JSONL loader + pipeline fixture

- **File**: `tests/adversarial/conftest.py`
- **Action**: CREATE
- **Implement**:
  - `load_jsonl(path) -> list[dict]` — skip lines starting with `#`, return parsed dicts
  - `@pytest.fixture(scope="session") full_pipeline_graph` — calls `build_graph()` with real validators (Toxic, PII in/out, Jailbreak, Compliance) + mock LLM that echoes input (to avoid API cost on every input-side test)
  - Helper to yield pytest.param with id-as-label from JSONL entries
- **Mirror**: `tests/api/conftest.py:62-99` (mock validator + graph build pattern)
- **Validate**: `uv run pytest tests/adversarial/ --collect-only` (discovery works)

### Task 9: Jailbreak pipeline adversarial test

- **File**: `tests/adversarial/test_jailbreak_pipeline.py`
- **Action**: CREATE
- **Implement**: parametrize over `jailbreak_external.jsonl`, run each through `full_pipeline_graph.invoke()`, assert `result["blocked"] is True`. Compute aggregate block rate; fail the test session if rate < 80% (write a session-finalizer hook in conftest). Mark whole module with `@pytest.mark.adversarial`.
- **Mirror**: existing parametrize pattern in `tests/unit/test_jailbreak.py`
- **Validate**: `uv run pytest tests/adversarial/test_jailbreak_pipeline.py -m adversarial -v` — block rate printed in summary

### Task 10: Toxic + PII pipeline tests

- **Files**:
  - `tests/adversarial/test_toxic_pipeline.py`
  - `tests/adversarial/test_pii_pipeline.py`
- **Action**: CREATE
- **Implement**: same shape as Task 9. PII test asserts both input-direction and output-direction blocks where applicable. Marker `@pytest.mark.adversarial`.
- **Validate**: `uv run pytest tests/adversarial/ -m adversarial -v` — all three suites green

### Task 11: Compliance pipeline test (network-gated)

- **File**: `tests/adversarial/test_compliance_pipeline.py`
- **Action**: CREATE
- **Implement**: parametrize over `compliance_handcrafted.jsonl`. Each entry has `expected_rule_violated: "R2"` etc. Requires `ANTHROPIC_API_KEY` — gated behind `@pytest.mark.network`. Assert `result["block_category"] == "compliance"` and `result["block_details"]["rule_violated"] == expected_rule`.
- **Mirror**: `tests/unit/test_compliance.py` for assertion shape
- **Validate**: `ANTHROPIC_API_KEY=... uv run pytest tests/adversarial/test_compliance_pipeline.py -m network -v`

### Task 12: Metrics script — substring-only vs substring+DeBERTa

- **File**: `scripts/measure_jailbreak_layers.py`
- **Action**: CREATE
- **Implement**:
  - Load `jailbreak_external.jsonl`
  - For each sample, run twice: `JailbreakValidator(use_deberta=False)` and `JailbreakValidator(use_deberta=True)`
  - Tally block rate per layer, separately for `lang=en` and `lang=pt-br`
  - Render a markdown table and write between `<!-- BEGIN: jailbreak-layer-metrics -->` … `<!-- END: jailbreak-layer-metrics -->` markers in `LIMITATIONS.md`
- **Mirror**: `scripts/ingest_banking_kb.py` for CLI scaffolding
- **Validate**: `uv run python scripts/measure_jailbreak_layers.py`; `grep -A10 "BEGIN: jailbreak-layer-metrics" LIMITATIONS.md` shows the new table

### Task 13: Update LIMITATIONS.md

- **File**: `LIMITATIONS.md`
- **Action**: UPDATE
- **Implement**:
  - Replace existing "Layered-defense comparison" tables with fenced markers so Task 12 can update them
  - Add explicit "Fixture closed-loop" subsection for PII + Compliance JSONL files
  - Add a new section: "Adversarial suite block rates (SCRUM-10)" with totals per category
- **Validate**: render in a markdown viewer; numbers match latest Task 12 output

### Task 14: Final integration check

- **Action**: VERIFY
- **Implement**:
  - `uv run pytest -m "not slow and not network" -q` — fast suite still green
  - `uv run pytest -m "adversarial and not network" -q` — adversarial offline tier passes ≥80% block rate
  - `ANTHROPIC_API_KEY=... uv run pytest -m "adversarial and network" -q` — compliance suite passes (manual)
- **Validate**: all three commands exit 0

---

## Validation

```bash
# Lint
uv run ruff check .
uv run ruff format --check .

# Fast tests (CI-equivalent)
uv run pytest -m "not slow and not network" -q

# Adversarial offline tier
uv run pytest tests/adversarial/ -m "adversarial and not network" -v

# Adversarial network tier (manual, with API key)
ANTHROPIC_API_KEY=... uv run pytest tests/adversarial/ -m "adversarial and network" -v

# Metrics refresh
uv run python scripts/measure_jailbreak_layers.py
git diff LIMITATIONS.md

# Ingest carry-over doc
uv run python scripts/ingest_banking_kb.py
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Block rate <80% on PT-BR JailbreakBench translations | Investigate per `building-rigorously.md §3`; document the gap in LIMITATIONS.md rather than tuning the threshold down |
| RealToxicityPrompts subset is EN-heavy → distribution differs from HateBR | Keep RTP as separate ID-prefix (`rtp_en_*`) so block-rate breakdown reveals it |
| Translation cost / quality from Claude | One-shot, cached output; ~25 prompts × ~200 tokens = trivial cost. Manual diff review |
| `use_deberta=False` couples measurement concern to production code | Justify in docstring as measurement hook (`building-rigorously.md §2`) |
| Compliance test flakiness (Claude Haiku non-determinism) | Use `temperature=0.0` (already set); accept ≥80% not 100% |
| Fixture JSONL vs `.py` Python fixtures — two sources of truth | Clear separation: `.py` for unit tests, `.jsonl` for adversarial/integration |
| Adversarial suite slow → impacts dev loop | `@pytest.mark.adversarial` opt-in; not in default run |

---

## Acceptance Criteria

- [ ] Task 0: `data/banking_kb/09_produtos_investimento.md` ingested; semantic search for "investir 10 mil reais" returns it in top-3
- [ ] `tests/adversarial/fixtures/jailbreak_external.jsonl` has ≥20 lines (≥10 PT-BR translations)
- [ ] `tests/adversarial/fixtures/toxic_external.jsonl` has ≥20 lines from HateBR + RealToxicityPrompts
- [ ] PII + Compliance handcrafted JSONL files include `"closed_loop": true` flag in header
- [ ] `uv run pytest tests/adversarial/ -m "adversarial and not network"` — block rate ≥80% on jailbreak and toxic
- [ ] Substring-only vs substring+DeBERTa block-rate table is real numbers, not "TBD"
- [ ] `LIMITATIONS.md` has fenced markers with populated tables
- [ ] All previously-green tests still pass (`pytest -m "not slow and not network"`)
- [ ] Ruff lint + format clean
