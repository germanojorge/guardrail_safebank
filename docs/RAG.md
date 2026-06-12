# RAG Architecture Decision Record

_Last updated: 2026-06-12 (SCRUM-40). All numbers trace to `models/eval/` — see footnotes._

---

## 1. Chunking Strategy

**Implementation**: `scripts/ingest_itau_faq.py` + `scripts/_faq_data.py`.

Each row of `Itau-Unibanco/FAQ_BACEN` (train split) becomes one chunk: `Pergunta: …\nResposta: …`. The HF `test` split is held out for eval (`data/eval/faq_bacen_eval.jsonl`). Point IDs are deterministic UUID5 keys on `itau_faq:{doc_id}`; metadata includes `doc_id` (`train_{i}`), `source: itau_faq_bacen`, and `chunk_idx`.

Production corpus: **1305 chunks** in Qdrant collection `itau_faq` (train split only).

### Rejected alternatives

| Alternative | Why rejected for this corpus |
|-------------|------------------------------|
| **Fixed-size + overlap** | FAQ rows are already atomic Q/A pairs; splitting would break answer completeness. |
| **Semantic chunking** | Unnecessary on pre-segmented FAQ data. |
| **Parent-document / small-to-big** | Each FAQ row is already the right retrieval unit for this use case. |

---

## 2. Vector Store — Qdrant

Collection `itau_faq`, cosine distance. Qdrant was chosen over in-memory FAISS or ChromaDB because:

- **Open-source and self-hosted** — no external API, no data leaves the Docker network.
- **Native metadata filters** — enables future filtering by document category, date, or product without a post-retrieval step.
- **Docker Compose fit** — single container, no persistent disk setup beyond a named volume.
- **Simple Python adapter** — the `VectorStore` Protocol in `guardrails/adapters/vector_store.py` wraps Qdrant's client; switching to OpenSearch (Bedrock) is a one-class swap.

See also ADR-002 (LangGraph standalone) and ADR-006 (local embeddings).

---

## 3. Embedding Model Selection

### Bake-off (faq_bacen — 373 queries, 1678 corpus docs) [^bakeoff]

| Model | dim | prefix | recall@1 | recall@3 | recall@5 | MRR@10 | nDCG@10 | latency ms/q |
|-------|-----|--------|----------|----------|----------|--------|---------|--------------|
| e5-small (prev) | 384 | e5 | 0.4316 | 0.6086 | 0.6836 | 0.5354 | 0.5891 | 22.7 |
| **e5-base (shipped)** | 768 | e5 | 0.4826 | 0.6756 | **0.7480** | 0.5885 | 0.6390 | 55.2 |
| MiniLM-L12-v2 | 384 | none | 0.2735 | 0.4424 | 0.4960 | 0.3718 | 0.4222 | 22.3 |
| itau-finetuned | 384 | — | SKIPPED — corrupted safetensors header | | | | | |

[^bakeoff]: Source: `models/eval/bakeoff_faq_bacen_summary.json` + `bakeoff_faq_bacen.md` (2026-06-11).

### Dimension trade-off

`intfloat/multilingual-e5-base` (768-dim) gains **+6.4pp recall@5** on faq_bacen (0.6836 → 0.7480) at the cost of ~300MB extra model weight (~120MB → ~420MB) and ~32ms extra CPU encoding latency per query (22.7 ms → 55.2 ms). The recall gain is material; the latency cost is acceptable for a single-query chatbot flow.

**E5 prefix convention**: the adapter (`guardrails/adapters/embedding.py`) transparently prepends `query:` to user queries and `passage:` to ingested chunks. Callers are unaware of this convention; it is encapsulated in `apply_prefixes`.

---

## 4. Retrieval Strategy

Pipeline order (implemented in `guardrails/pipeline/nodes.py` — `build_nodes`):

```
encode query (e5-base, query: prefix)
    → Qdrant cosine search (top_n=20 candidates)
    → score_threshold filter (0.82)
    → cross-encoder reranker (top_k=3 output)
    → top-3 chunks → LLM
```

### Reranker — before / after [^reranker]

| Configuration | recall@3 | recall@5 | mrr@10 | ndcg@10 |
|---------------|----------|----------|--------|---------|
| Dense only (e5-base, top-3) | 0.6756 | 0.6756 | 0.5648 | 0.5932 |
| Dense-20 + CE reranker (top-3) | **0.6836** | 0.7426 | **0.6230** | **0.6668** |

Deltas vs dense baseline: **+1.2pp recall@3 / +10.3pp mrr@10 / +12.4pp ndcg@10**. recall@10 with reranker = 0.8043.

> Note: dense-only recall@5 = recall@3 = 0.6756 because `final_top_k=3` with no reranker retains only the 3 cosine hits. With the reranker, 20 candidates are scored by the cross-encoder before slicing, so recall@5 and recall@10 become meaningful.

CE model: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (multilingual MS MARCO).

**Decision**: reranker enabled (`retrieval.reranker.enabled: true`). The +1.2pp recall@3 is modest; the MRR/nDCG gains (+10.3pp / +12.4pp) reflect meaningfully better ranking of the top hit and are the primary rationale. Per building-rigorously §7: the recall@3 delta is small and is stated plainly — the MRR/nDCG story is the honest one.

[^reranker]: Source: `models/eval/retrieval_before_after.md` (2026-06-12, SCRUM-39). Run files: `faq_bacen__intfloat__multilingual-e5-base__20260612_031232.json` (manual dense), `faq_bacen__intfloat__multilingual-e5-base__20260612_033951.json` (CE reranker).

### Score threshold sweep [^threshold]

Sweep on faq_bacen on-topic queries + 20 `_DEFAULT_OUT_OF_SCOPE` seeds:

| threshold | recall@3 (in-scope) | off-topic rejection % |
|-----------|--------------------|-----------------------|
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

**Analysis**: there is no clean knee — rejection only starts at 0.78 and saturates at 0.84. The selected operating point is **0.82**: 65% off-topic rejection with zero in-domain recall cost (recall@3 stays 0.6756). Threshold 0.84 achieves 100% rejection at a cost of only −0.4pp recall (0.6729), but 0.82 was preferred to preserve recall@3. Config: `retrieval.score_threshold: 0.82`.

Off-topic seeds are also used by the `out_of_scope` validator (which runs before retrieval). The threshold here is a defense-in-depth layer for queries that pass the scope guard but have low semantic similarity to the corpus.

[^threshold]: Source: `models/eval/retrieval_before_after.md` (2026-06-12, SCRUM-39).

---

## 5. Eval Methodology and Leakage Declaration

### Primary eval dataset

| Dataset | Source | Role | Leakage status |
|---------|--------|------|----------------|
| **faq_bacen** | FAQ_BACEN (Hugging Face) — frozen JSONL in `data/eval/` | Bake-off + retrieval eval; 373 test queries, 1678 corpus docs (train+test answers) | Low leakage: public HF dataset; **train** ingested into Qdrant, **test** held out for eval. Classified as "external-ish". |

### Anti-tautology gate

`run_eval_manual` dense-only recall@3 = **0.6756** matches `InformationRetrievalEvaluator` recall@3 = **0.6756** exactly (per `models/eval/retrieval_before_after.md`). The two evaluation paths (manual numpy cosine vs sentence-transformers `InformationRetrievalEvaluator`) produce identical results on the faq_bacen dense baseline, confirming neither is self-validating. This is the anti-tautology gate per building-rigorously §3.

### Known eval-vs-production gap

`run_eval_manual` uses numpy cosine directly; production queries go through Qdrant's HNSW index. Minor score differences due to HNSW approximation may exist but are not currently quantified. See `LIMITATIONS.md` — "In-memory eval vs Qdrant production".

---

## 6. Reproducible Commands

```bash
# Activate env (heavy-model caches redirected via .env)
set -a; source .env; set +a

# Freeze FAQ_BACEN splits — network, run once
uv run python scripts/eval_retrieval.py --freeze

# Bake-off across models → models/eval/bakeoff_faq_bacen.md
uv run python scripts/bakeoff_embeddings.py

# Single-model eval (e5-base default)
uv run python scripts/eval_retrieval.py

# With reranker
uv run python scripts/eval_retrieval.py \
    --reranker cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --top-n 20

# Threshold sweep
uv run python scripts/eval_retrieval.py --threshold-sweep

# Re-ingest after a dim change (384→768 requires dropping/recreating Qdrant collection)
docker compose run --rm ingest
```

Flag reference (from `scripts/eval_retrieval.py` argparse):
- `--dataset` — `faq_bacen` (default, only option)
- `--reranker` — HF cross-encoder model id
- `--top-n` — dense candidate count before reranking (default: 20)
- `--threshold` — minimum cosine score (default: None)
- `--threshold-sweep` — sweep 0.70–0.92 and report rejection vs recall
- `--freeze` — regenerate frozen JSONL from HF (network required, run once)
