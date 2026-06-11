# Plan: Model Bake-off — Justify Embedding Model + Dimensions by Measurement (SCRUM-38)

## Summary

Run the existing retrieval harness (`scripts/eval_retrieval.py`, built in SCRUM-37) across **four embedding models on the same frozen FAQ_BACEN split**, capture per-query CPU latency, and emit a single comparison table (`model × dim × recall@5 × MRR@10 × nDCG@10 × latency/query`). The crux is **per-model prefixing**: E5 models require `query:`/`passage:` prefixes; the MiniLM base and the existing fine-tune (BERT/MiniLM-based, trained *without* prefixes) must run **prefix-free**, or the comparison is invalid. Add latency instrumentation + a `prefix_style` parameter to the harness, write a small bake-off driver, then ship the winner to `config.yaml` **only after** an anti-regression sanity-check on `banking_kb`.

## User Story

As a candidate
I want to compare embedding models on the same metric and frozen split
So that I justify "why this model / why 384 dims" with data instead of vibes.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (extends SCRUM-37 harness) + DATA/DECISION |
| Complexity | MEDIUM |
| Systems Affected | `scripts/eval_retrieval.py`, new `scripts/bakeoff_embeddings.py`, `config.yaml`, `models/eval/`, tests |
| Jira Issue | SCRUM-38 |
| Blocked by | SCRUM-37 (harness) — DONE |
| Blocks | Story 4 (docs need this table) |

---

## Critical Design Decision: Per-Model Prefixing (the thing that makes this correct)

The current harness hardcodes E5 prefixes in `run_eval` (`scripts/eval_retrieval.py:151-152`):

```python
prefixed_corpus = {k: f"passage: {v}" for k, v in corpus.items()}
prefixed_queries = {k: f"query: {v}" for k, v in queries.items()}
```

This is correct for the two E5 models but **wrong** for:
- `paraphrase-multilingual-MiniLM-L12-v2` — never trained with E5 prefixes.
- `models/itau-embedding-finetuned` — **BERT/MiniLM-based** (`config.json`: `model_type: bert`, `hidden_size: 384`, `vocab_size: 250037`), and `config_sentence_transformers.json` shows empty `prompts` (`"query": ""`, `"document": ""`). The legacy fine-tune evaluator ran **without** prefixes — already flagged as D4 in `run_eval`'s docstring (`scripts/eval_retrieval.py:145-147`).

Injecting literal `query: ` / `passage: ` tokens into MiniLM inputs handicaps those models unfairly → the bake-off would measure the wrong thing (building-rigorously §5). **Therefore prefixing must be a per-model parameter**, set by the driver:

| Model | dim | prefix_style |
|-------|-----|--------------|
| `intfloat/multilingual-e5-small` (current) | 384 | `e5` |
| `intfloat/multilingual-e5-base` | 768 | `e5` |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | `none` |
| `models/itau-embedding-finetuned` (local) | 384 | `none` |

> **Honesty note for the table & docs:** even with correct prefixing, an E5-vs-MiniLM comparison is not perfectly apples-to-apples (different pretraining recipes). The fine-tune was trained on FAQ_BACEN train split, so a strong FAQ_BACEN score may be **train-distribution overfit** — exactly why the AC mandates the `banking_kb` anti-regression gate before shipping. State this explicitly in the run record / docs rather than hiding it.

---

## Patterns to Follow

### Harness entry points (reuse, don't reinvent)
```python
# SOURCE: scripts/eval_retrieval.py:88-129  (load_frozen + run_eval + extract_metrics)
corpus, queries, relevant_docs = load_frozen("faq_bacen", data_dir)
results = run_eval(model_name, corpus, queries, relevant_docs, name="faq_bacen")
metrics = extract_metrics(results, "faq_bacen")
```

### env_bootstrap import MUST come first (HF cache redirection)
```python
# SOURCE: scripts/eval_retrieval.py:23
import guardrails.env_bootstrap  # noqa: F401  # DEVE vir antes de datasets/transformers
```

### Run-record JSON shape (extend, keep keys stable)
```python
# SOURCE: scripts/eval_retrieval.py:283-294  + models/eval/faq_bacen__*.json
{"model", "dataset", "prefixes_applied", "closed_loop", "n_queries",
 "n_corpus", "timestamp", "seed", "metrics"}  # add: "prefix_style", "latency_ms_per_query"
```

### Tests: pure functions, mock, no network; heavy model behind `@slow`
```python
# SOURCE: scripts/eval_retrieval.py — extract_metrics/render_markdown are pure
# tests/unit/test_eval_retrieval.py (19 tests) covers them; mirror its style.
# pyproject markers: "slow" (heavy ML), "network" (downloads). Bake-off run itself is manual/slow.
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/eval_retrieval.py` | UPDATE | Make prefixing a param (`prefix_style: "e5"\|"none"`, default `"e5"` for back-compat); add optional latency measurement; thread `--prefix-style` CLI flag + record `prefix_style` in JSON |
| `scripts/bakeoff_embeddings.py` | CREATE | Driver: loop the 4 models with correct prefix styles on `faq_bacen`, collect metrics + latency, render the F-2 comparison table (stdout + markdown file), write per-model run JSONs |
| `models/eval/bakeoff_faq_bacen.md` | CREATE | Committed comparison table artifact (the F-2 deliverable for docs/Story 4) |
| `models/eval/*.json` | CREATE (generated) | Per-model run records (4 faq_bacen + winner banking_kb sanity) |
| `config.yaml` | UPDATE | Ship winner under `embedding.model` **only after** banking_kb anti-regression check passes |
| `tests/unit/test_eval_retrieval.py` | UPDATE | Add cases for `prefix_style="none"` (no prefixes baked) and latency-field plumbing; keep all mock/no-network |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Parametrize prefixing in `run_eval`

- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: Add `prefix_style: str = "e5"` param to `run_eval`. When `"e5"`, bake `query:`/`passage:` (current behavior). When `"none"`, pass corpus/queries unmodified. Validate against `{"e5","none"}` and raise `ValueError` otherwise. Update the docstring (currently asserts prefixes always applied — that's now conditional; building-rigorously §4, fix the doc in the same change).
- **Mirror**: `scripts/eval_retrieval.py:131-170`
- **Validate**: `uv run ruff check scripts/eval_retrieval.py`

### Task 2: Add latency-per-query measurement

- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: Add a helper `measure_latency_ms_per_query(model, queries, prefix_style, warmup=3, repeats=N) -> float`. Warm up the model (first encode is slow/JIT), then time `model.encode([single_query])` with `batch_size=1` per query across all eval queries (single-query encode mirrors production `embed_queries`), return mean ms/query. CPU-only, `normalize_embeddings=True` to mirror `embedding.py:55-60`. Note in the run JSON that latency is noisy/machine-dependent (don't over-claim precision).
- **Mirror**: `guardrails/adapters/embedding.py:55-71` (encode call shape)
- **Validate**: `uv run ruff check scripts/eval_retrieval.py`

### Task 3: Thread `--prefix-style` through CLI + run JSON

- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: Add `--prefix-style {e5,none}` (default `e5`) to `argparse`. Pass into `run_eval`. Add `"prefix_style"` and `"latency_ms_per_query"` to the run payload; set `"prefixes_applied"` to `prefix_style == "e5"`. Keep existing keys/order stable so SCRUM-37 baseline JSONs stay diff-comparable.
- **Mirror**: `scripts/eval_retrieval.py:262-307` (argparse + payload)
- **Validate**: `uv run python scripts/eval_retrieval.py --help` shows `--prefix-style`

### Task 4: Create the bake-off driver

- **File**: `scripts/bakeoff_embeddings.py`
- **Action**: CREATE
- **Implement**: `import guardrails.env_bootstrap` first. Define the 4 `(model_id, dim, prefix_style)` rows in a constant list. For each: `load_frozen("faq_bacen")` (load once, reuse), `run_eval(..., prefix_style=...)`, `extract_metrics`, `measure_latency_ms_per_query`. Collect into rows; render an F-2 markdown table with columns `model | dim | recall@5 | MRR@10 | nDCG@10 | latency_ms/q`, print to stdout AND write to `models/eval/bakeoff_faq_bacen.md`. Also write each model's run JSON via `write_run_json`. Print a "winner" suggestion (highest recall@5, tie-break MRR@10) but **do not** auto-edit config. Add `--dataset` passthrough (default `faq_bacen`) so the same driver runs the `banking_kb` sanity check in Task 6.
- **Mirror**: `scripts/eval_retrieval.py:262-310` (main flow), table style `render_markdown` (`scripts/eval_retrieval.py:243-247`)
- **Validate**: `uv run ruff check scripts/bakeoff_embeddings.py`; dry `--help`

### Task 5: Run the bake-off on faq_bacen + commit the table

- **File**: `models/eval/bakeoff_faq_bacen.md` (+ 4 run JSONs)
- **Action**: CREATE (generated artifacts)
- **Implement**: `uv run python scripts/bakeoff_embeddings.py` (downloads e5-base + MiniLM via HF; CPU; minutes-scale on 1678-doc corpus × 373 queries × 4 models). Inspect the table. **Sanity gate (building-rigorously §3):** no model should post absurd recall@5 (≈1.0) on the external split — if the fine-tune does, suspect train/test leakage and investigate before trusting it. Record the winner.
- **Mirror**: baseline run `models/eval/faq_bacen__intfloat__multilingual-e5-small__*.json`
- **Validate**: table has 4 rows, recall monotone per row, latency populated; e5-small row matches SCRUM-37 baseline (recall@5 ≈ 0.6836) — regression check that refactor didn't change numbers

### Task 6: Anti-regression sanity-check on `banking_kb` before shipping

- **File**: winner run JSON on `banking_kb`
- **Action**: CREATE (generated)
- **Implement**: Run the winner **and** current e5-small on `--dataset banking_kb`. The AC explicitly warns the fine-tune may overfit FAQ_BACEN and **regress the demo KB**. Decision rule: ship the winner to `config.yaml` **only if** its `banking_kb` recall@5/MRR does **not** regress vs current e5-small (0.875 / 0.8125). If it regresses, keep e5-small and document the bake-off as a measured-tradeoff talking point (a negative result is still a result — building-rigorously §7).
- **Mirror**: `models/eval/banking_kb__intfloat__multilingual-e5-small__*.json` (compare against these numbers)
- **Validate**: winner's banking_kb metrics ≥ e5-small's, or decision recorded to NOT ship

### Task 7: Ship winner to config (conditional on Task 6)

- **File**: `config.yaml`
- **Action**: UPDATE (only if Task 6 passes the gate)
- **Implement**: Set `embedding.model` to the winner. If the winner is prefix-free (MiniLM/fine-tune), this is a **behavioral change for the live pipeline** — `embedding.py` unconditionally adds E5 prefixes (`embed_queries`/`embed_passages`, `embedding.py:63-71`). Flag this as a follow-up risk (see Risks); for a prefix-free winner, either (a) keep e5-small for the demo and ship the finding as a talking point, or (b) scope a separate change to make `embedding.py` prefixing model-aware. **Default expectation: e5-small or e5-base wins on the external split; if e5-base wins, weigh its 768-dim latency/memory cost against the recall gain (that IS the "dimensions as measured trade-off" deliverable).**
- **Mirror**: `config.yaml` `embedding:` block
- **Validate**: `uv run python -c "from guardrails.config import load_config; print(load_config())"` (or equivalent loader) succeeds

### Task 8: Update tests

- **File**: `tests/unit/test_eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: Add unit cases: `run_eval` with `prefix_style="none"` does NOT prepend `query:`/`passage:` (assert on a mock/spy or refactor prefix-baking into a tiny pure helper `apply_prefixes(texts, role, style)` and unit-test that directly — preferred, keeps it network-free); invalid `prefix_style` raises `ValueError`; run payload carries `prefix_style` + `latency_ms_per_query`. Keep everything mock/no-network; heavy model paths stay `@slow`.
- **Mirror**: `tests/unit/test_eval_retrieval.py` existing 19 mock tests
- **Validate**: `uv run pytest tests/unit/test_eval_retrieval.py -q`

---

## Validation

```bash
# Lint
uv run ruff check scripts/ tests/

# Unit tests (mock, no network)
uv run pytest tests/unit/test_eval_retrieval.py -q

# Harness back-compat: e5-small baseline unchanged (regression guard)
uv run python scripts/eval_retrieval.py --dataset faq_bacen   # recall@5 ≈ 0.6836

# Full bake-off (slow, network on first run for HF downloads)
uv run python scripts/bakeoff_embeddings.py

# Anti-regression gate before any config change
uv run python scripts/bakeoff_embeddings.py --dataset banking_kb
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| **Wrong prefixing invalidates comparison** (E5 prefixes on MiniLM/fine-tune) | Per-model `prefix_style`; fine-tune/MiniLM → `none`. Core of Tasks 1–4. |
| **Fine-tune overfits FAQ_BACEN, regresses demo KB** | Mandatory `banking_kb` gate (Task 6); ship only on no-regression. |
| **Prefix-free winner breaks live pipeline** — `embedding.py:63-71` always adds E5 prefixes | Surface as explicit decision in Task 7; don't silently ship a model that the runtime then mis-prefixes. Prefer e5 winner for the demo, or scope `embedding.py` prefix-awareness separately. |
| **Latency numbers noisy / machine-dependent** | Warmup + mean over all queries; label as indicative CPU latency in the artifact, not a benchmark guarantee. |
| **Refactor silently changes e5-small numbers** | Regression check in Task 5: e5-small recall@5 must still ≈ 0.6836 vs SCRUM-37 baseline. |
| **HF download of e5-base/MiniLM in a no-network env** | env_bootstrap redirects caches; first run needs network (mark expectation), subsequent runs offline. |

---

## Acceptance Criteria

- [ ] Bake-off runs the harness over all 4 models on the **same frozen faq_bacen split**, each with correct `prefix_style`.
- [ ] Comparison table `model × dim × recall@5 × MRR@10 × nDCG@10 × latency/query (CPU)` committed (`models/eval/bakeoff_faq_bacen.md`).
- [ ] Decision recorded as a **measured** dims trade-off (quality × latency × memory), not an assertion.
- [ ] Winner shipped to `config.yaml` **only after** the `banking_kb` anti-regression check (or documented decision to keep e5-small).
- [ ] e5-small baseline numbers unchanged post-refactor (regression guard).
- [ ] Unit tests pass; lint clean; closed-loop/overfit caveats stated honestly in the artifact.
