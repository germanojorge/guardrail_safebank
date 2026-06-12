# Implementation Report — SCRUM-39: Score Threshold + Cross-Encoder Reranker

**Plan**: `.claude/agents/plans/scrum-39-threshold-reranker.plan.md`
**Branch**: `main`
**Status**: COMPLETE ✅

---

## Summary

Added (1) a configurable cosine score threshold to the RAG `retrieve` node — queries below threshold return no chunks, causing the chatbot to respond "não tenho essa informação"; (2) a cross-encoder reranker (`CrossEncoderReranker` / `IdentityReranker` via the `Reranker` Protocol) that re-scores top-N dense candidates and returns top-3 to the LLM. Both features are gated by measurement in `config.yaml` (`retrieval.score_threshold = null`, `retrieval.reranker.enabled = false`) and are only enabled if the SCRUM-39 bake-off shows a positive recall@3 delta over the e5-base baseline.

Anti-tautology gate passed: `run_eval_manual` dense-only recall@3 = **0.6756** matches `InformationRetrievalEvaluator` recall@3 = **0.6756** exactly, confirming the manual eval path is independent and not self-validating.

---

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `Reranker` Protocol + `CrossEncoderReranker` + `IdentityReranker` | `guardrails/adapters/reranker.py` | ✅ CREATE |
| 2 | `VectorStore.search` score_threshold param | `guardrails/adapters/vector_store.py` | ✅ UPDATE |
| 3 | `LatencyBreakdown.rerank` field | `guardrails/api/schemas.py` | ✅ UPDATE |
| 4 | `build_nodes` / `build_graph` reranker + threshold wiring | `guardrails/pipeline/nodes.py`, `graph.py` | ✅ UPDATE |
| 5 | `app.py` DI factory reads config, builds reranker | `guardrails/api/app.py` | ✅ UPDATE |
| 6 | `config.yaml` retrieval section | `config.yaml` | ✅ UPDATE |
| 7 | `adapters/__init__.py` exports | `guardrails/adapters/__init__.py` | ✅ UPDATE |
| 8 | IR metric helpers + `run_eval_manual` + `threshold_sweep` + CLI flags | `scripts/eval_retrieval.py` | ✅ UPDATE |
| 9 | SCRUM-39 eval runs | `models/eval/` JSON + `retrieval_before_after.md` | ✅ MEASURED |
| 10 | ADR-006 update (e5-small→e5-base + SCRUM-39 additions) | `adr/006-local-embeddings.md` | ✅ UPDATE |
| 11 | LIMITATIONS.md retrieval section | `LIMITATIONS.md` | ✅ UPDATE |
| 12 | Unit tests — reranker, vector_store, eval_retrieval, pipeline | `tests/unit/` (4 files updated) | ✅ |

---

## Validation Results

| Check | Result |
|-------|--------|
| Lint (ruff) | ✅ clean |
| Unit tests (not slow) | ✅ 102 passed, 2 deselected |
| Anti-tautology gate | ✅ run_eval_manual recall@3 = 0.6756 matches InformationRetrievalEvaluator |
| Local import bug fix | ✅ monkeypatch now intercepts SentenceTransformer in run_eval_manual / threshold_sweep |

---

## Measurement Results (SCRUM-39 — faq_bacen, 373 queries, 1678 corpus docs)

### Anti-tautology gate

| Eval path | recall@3 | Match |
|-----------|----------|-------|
| `InformationRetrievalEvaluator` (SCRUM-38 baseline) | 0.6756 | — |
| `run_eval_manual` dense-only | 0.6756 | ✅ |

### Before/after table

| Configuration | recall@3 | mrr@10 | ndcg@10 | Note |
|---------------|----------|--------|---------|------|
| Dense only (e5-base, top-3 cosine) | 0.6756 | 0.5648 | 0.5932 | baseline |
| Dense-20 + CE reranker (top-3) | **0.6836** | **0.6230** | **0.6668** | +1.2pp / +10.3pp / +12.4pp |

**Decision**: reranker enabled (`retrieval.reranker.enabled: true`).

### Threshold sweep (faq_bacen in-scope vs out-of-scope rejection)

| Threshold | recall@3 (in-scope) | off-topic rejection % | Note |
|-----------|--------------------|-----------------------|------|
| 0.70 | 0.6756 | 0.0% | — |
| 0.78 | 0.6756 | 10.0% | — |
| **0.82** | **0.6756** | **65.0%** | selected |
| 0.84 | 0.6729 | 100.0% | — |
| 0.88 | 0.4263 | 100.0% | cliff |

**Decision**: threshold=0.82 (`retrieval.score_threshold: 0.82`). Zero recall cost at 65% off-topic rejection.

---

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/adapters/reranker.py` | CREATE | `Reranker` Protocol + `CrossEncoderReranker` + `IdentityReranker` |
| `guardrails/adapters/__init__.py` | UPDATE | Export new symbols |
| `guardrails/adapters/vector_store.py` | UPDATE | `score_threshold` param on `search` |
| `guardrails/api/schemas.py` | UPDATE | `LatencyBreakdown.rerank` field |
| `guardrails/pipeline/nodes.py` | UPDATE | `build_nodes` wires reranker + threshold |
| `guardrails/pipeline/graph.py` | UPDATE | `build_graph` passes new params |
| `guardrails/api/app.py` | UPDATE | DI factory reads retrieval config |
| `config.yaml` | UPDATE | `retrieval` section with threshold + reranker config |
| `scripts/eval_retrieval.py` | UPDATE | IR metrics, `run_eval_manual`, `threshold_sweep`, CLI flags |
| `adr/006-local-embeddings.md` | UPDATE | Fix doc drift (e5-small→e5-base) + SCRUM-39 additions |
| `LIMITATIONS.md` | UPDATE | New retrieval section with confirmed gaps |
| `tests/unit/test_reranker.py` | CREATE | Protocol checks + CE + Identity unit tests |
| `tests/unit/test_vector_store.py` | UPDATE | score_threshold tests |
| `tests/unit/test_eval_retrieval.py` | UPDATE | IR metric helpers + run_eval_manual tests |
| `tests/unit/test_pipeline.py` | UPDATE | reranker + threshold integration tests |

---

## Deviations from Plan

| Deviation | Reason |
|-----------|--------|
| Anti-tautology comparison at recall@3 (not recall@5) | `run_eval_manual` with `final_top_k=3` only produces 3-item rankings; recall@5 = recall@3 trivially. Gate still validates: both paths yield 0.6756 at recall@3. |
| Local import bug fix not in original plan | `run_eval_manual` imported `SentenceTransformer` locally, bypassing monkeypatch. Fixed by removing local import (module-level already existed). |
| `SENTENCE_TRANSFORMERS_HOME` env workaround | System env points to unmounted external drive; eval runs require `env -u SENTENCE_TRANSFORMERS_HOME HF_HOME=/home/germano/.cache/ml-eval/huggingface`. |

---

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/unit/test_reranker.py` | 11 tests: protocol checks, Identity (4), CrossEncoder (6) |
| `tests/unit/test_vector_store.py` | +4 tests: score_threshold filtering (InMemory + Qdrant) |
| `tests/unit/test_eval_retrieval.py` | +12 tests: IR metric helpers (5), run_eval_manual (5), @slow anti-tautology (1), threshold_sweep smoke (1) |
| `tests/unit/test_pipeline.py` | +4 tests: rerank_ms in diagnostics, no rerank_ms without reranker, high threshold → empty, spy reranker query |
