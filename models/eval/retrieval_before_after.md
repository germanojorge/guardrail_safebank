# Retrieval — Before / After (SCRUM-39)

Dataset: **faq_bacen** — 373 queries, 1678 corpus docs, e5-base embeddings.

Anti-tautology gate (building-rigorously §1/§3): `run_eval_manual` dense-only recall@3 = **0.6756** matches `InformationRetrievalEvaluator` recall@3 = **0.6756** exactly. The manual eval path is not self-validating — it reproduces the frozen baseline from an independent computation path.

---

## Before / After — Reranker

| Configuration | recall@3 | recall@5 | mrr@10 | ndcg@10 | Note |
|---------------|----------|----------|--------|---------|------|
| Dense only (e5-base, top-3 cosine) | 0.6756 | 0.6756 | 0.5648 | 0.5932 | baseline |
| Dense-20 + CE reranker (top-3) | **0.6836** | 0.7426 | **0.6230** | **0.6668** | after (+1.2pp, +10.3pp, +12.4pp) |

**CE model**: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (multilingual MS MARCO)

**Decision**: reranker **enabled** (`retrieval.reranker.enabled: true`). Positive delta on recall@3 (+1.2pp) and large MRR/nDCG improvements.

> Note: dense-only recall@5 = recall@3 = 0.6756 because `final_top_k=3` (only top-3 cosine docs are kept when no reranker). With reranker, all 20 candidates are ranked by CE before slicing to top-3, producing meaningful recall@5 and recall@10 (0.8043).

---

## Threshold Sweep

Sweep cosine threshold 0.70–0.92 on faq_bacen on-topic queries + off-topic seeds from `_DEFAULT_OUT_OF_SCOPE` (different source from corpus — building-rigorously §1).

| threshold | recall@3 | off-topic rejection % |
|-----------|----------|-----------------------|
| 0.70 | 0.6756 | 0.0% |
| 0.72 | 0.6756 | 0.0% |
| 0.74 | 0.6756 | 0.0% |
| 0.76 | 0.6756 | 0.0% |
| 0.78 | 0.6756 | 10.0% |
| 0.80 | 0.6756 | 25.0% |
| **0.82** | **0.6756** | **65.0%** | ← selected |
| 0.84 | 0.6729 | 100.0% |
| 0.86 | 0.6139 | 100.0% |
| 0.88 | 0.4263 | 100.0% |
| 0.90 | 0.1475 | 100.0% |
| 0.92 | 0.0268 | 100.0% |

**Analysis**: No "clean knee" — rejection only starts at 0.78 and reaches 100% at 0.84. The selected operating point is **0.82**: 65% off-topic rejection with zero in-domain recall cost (recall@3 stays 0.6756). Config set to `retrieval.score_threshold: 0.82`.

**Threshold 0.84** (alternative): 100% off-topic rejection at -0.4pp recall cost (0.6729). Chose 0.82 to preserve recall@3.

**Note**: Off-topic rejection numbers are computed on 20 `_DEFAULT_OUT_OF_SCOPE` seeds. These seeds are also used by the `out_of_scope` validator (which runs before retrieval). The threshold here is a defense-in-depth layer for queries that pass the out_of_scope guard but have low semantic similarity to the corpus.

---

## Source JSON files

| Run | File |
|-----|------|
| e5-base baseline (InformationRetrievalEvaluator) | `faq_bacen__intfloat__multilingual-e5-base__20260612_030818.json` |
| e5-base manual dense-only (anti-tautology gate) | `faq_bacen__intfloat__multilingual-e5-base__20260612_031232.json` |
| e5-base + CE reranker | `faq_bacen__intfloat__multilingual-e5-base__20260612_033951.json` |
