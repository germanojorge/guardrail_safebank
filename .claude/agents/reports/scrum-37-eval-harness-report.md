# Implementation Report

**Plan**: `.claude/agents/plans/scrum-37-eval-harness.plan.md`
**Branch**: `main`
**Status**: COMPLETE

## Summary

Built `scripts/eval_retrieval.py` — a self-contained, reproducible retrieval eval harness that reads frozen JSONL splits, applies E5 prefixes, runs `InformationRetrievalEvaluator`, and emits recall@{1,3,5,10}, MRR@10, nDCG@10, MAP@10 as markdown table + JSON run record. Committed baseline e5-small numbers (faq_bacen, external test split, leakage-free).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Harness skeleton + CLI | `scripts/eval_retrieval.py` | ✅ |
| 2a | Extract `load_faq_data` to shared module | `scripts/_faq_data.py` + `scripts/finetune_itau_embedding.py` | ✅ |
| 2 | `--freeze` flag → frozen JSONL | `data/eval/faq_bacen_corpus.jsonl`, `data/eval/faq_bacen_eval.jsonl` | ✅ |
| 3 | `load_frozen` loader (disk-only) | `scripts/eval_retrieval.py` | ✅ |
| 4 | E5 prefix baking + IR evaluator | `scripts/eval_retrieval.py` | ✅ |
| 5 | Metrics extraction + JSON + markdown | `scripts/eval_retrieval.py` | ✅ |
| 6 | `banking_kb_eval.jsonl` smoke set (16 q, closed-loop) | `data/eval/banking_kb_eval.jsonl` | ✅ |
| 7 | FAQ_BACEN baseline e5-small committed | `models/eval/faq_bacen__intfloat__multilingual-e5-small__*.json` | ✅ |
| 8 | Unit tests (mock, no network) | `tests/unit/test_eval_retrieval.py` | ✅ |
| 9 | `.gitignore` unblocks `data/eval/` + `models/eval/` | `.gitignore` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `--help` | ✅ |
| `--freeze` runs and is deterministic | ✅ (diff empty on 2nd run) |
| `banking_kb` eval (fast smoke) | ✅ recall@1=0.75, MRR@10=0.8125 |
| FAQ_BACEN baseline e5-small | ✅ recall@1=0.43, recall@10=0.76, MRR@10=0.54, nDCG@10=0.59 |
| 0 orphan ids in banking_kb_eval.jsonl | ✅ |
| ruff lint | ✅ (0 errors) |
| Unit tests (19 tests, mock) | ✅ 19 passed |

## Baseline Metrics (e5-small, faq_bacen, external test split)

| Metric | Score |
|--------|-------|
| map@10 | 0.5354 |
| mrr@10 | 0.5354 |
| ndcg@10 | 0.5891 |
| recall@1 | 0.4316 |
| recall@3 | 0.6086 |
| recall@5 | 0.6836 |
| recall@10 | 0.7587 |

**Sanity check (§3 building-rigorously):** recall@1 = 0.43 is NOT absurdly high (< 0.95). Numbers are plausible for e5-small/384 on a 1678-doc PT-BR corpus without fine-tuning. Recall monotone: recall@1 ≤ recall@3 ≤ recall@5 ≤ recall@10 ✓.

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `scripts/eval_retrieval.py` | CREATE | ~300 LOC, full harness |
| `scripts/_faq_data.py` | CREATE | Shared `load_faq_data` + `build_evaluator` |
| `scripts/finetune_itau_embedding.py` | UPDATE | Imports from `_faq_data` instead of inline defs |
| `data/eval/faq_bacen_corpus.jsonl` | CREATE | 1678 rows, frozen |
| `data/eval/faq_bacen_eval.jsonl` | CREATE | 373 rows, frozen |
| `data/eval/banking_kb_eval.jsonl` | CREATE | 16 queries, closed-loop (declared) |
| `models/eval/faq_bacen__*.json` | CREATE | Baseline run record |
| `models/eval/banking_kb__*.json` | CREATE | Smoke run record |
| `models/eval/.gitkeep` | CREATE | Directory marker |
| `tests/unit/test_eval_retrieval.py` | CREATE | 19 unit tests |
| `.gitignore` | UPDATE | Unblock `data/eval/` + `models/eval/` |

## Deviations from Plan

- **eval_retrieval.py `--help` validation uses `uv run python ...`** not `uv run python scripts/...` — both work identically since env_bootstrap runs before any model import.
- **`python -c "from scripts._faq_data import ..."` requires `uv run`** because `langgraph` is a uv-only dep. Plan assumption that system Python has all deps is incorrect for this project; all validations work fine with `uv run`.
- **`_faq_data.py` uses `sentence_transformers.sentence_transformer.evaluation`** (non-deprecated path) instead of the deprecated `sentence_transformers.evaluation`.
- **16 queries** in banking_kb_eval.jsonl (plan said ~15) — one extra query added for better coverage of the sigilo_pix doc.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/unit/test_eval_retrieval.py` | `extract_metrics` (6 cases), `render_markdown` (4 cases), `load_frozen faq_bacen` (3 cases), `load_frozen banking_kb` (2 cases), `freeze determinism` (2 cases), `write_run_json` (2 cases), `@slow` real e5-small recall monotone (1 case) |
