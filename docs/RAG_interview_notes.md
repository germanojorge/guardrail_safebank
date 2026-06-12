# RAG — Interview Cheat-Sheet

_Quick Q&A for the 5 core technical questions + common follow-ups. Each answer gives the killer number and cross-links the full analysis in `docs/RAG.md`._

---

## Core Questions

### 1. Why e5-base over e5-small or MiniLM?

The bake-off on faq_bacen (373 queries, 1678 corpus docs) showed e5-base at **recall@5 = 0.7480** vs e5-small at 0.6836 (+6.4pp) and MiniLM-L12-v2 at 0.4960 (+25.2pp). e5-base also passes the banking_kb anti-regression gate (+6.25pp recall@5, 0.875 → 0.9375). MiniLM has no prefix convention, which hurts PT-BR FAQ retrieval significantly. e5-small was the previous model; e5-base is a direct upgrade within the same E5 family (same prefix convention, same API surface in the adapter).

→ Full bake-off table: [docs/RAG.md §3](RAG.md#3-embedding-model-selection)

### 2. Why 768 dims? Memory / latency trade-off?

768 dims cost ~300MB extra model weight (~120MB → ~420MB) and ~32ms extra CPU latency per query (22.7 → 55.2 ms). For a single-query chatbot, the +32ms is absorbed into the total LLM latency (hundreds of ms). The recall gain (+6.4pp on faq_bacen, +6.25pp on banking_kb) is material and one-time. The weight increase matters at scale — for AWS Bedrock/ECS deployment, Titan Embeddings v2 (1536-dim) at 0 marginal cost would be the migration path (see Extras in CLAUDE.md).

→ [docs/RAG.md §3 — Dimension trade-off](RAG.md#dimension-trade-off)

### 3. Why Qdrant over FAISS or ChromaDB?

Four reasons: (1) native metadata filters for future filtering by product/category without post-retrieval work; (2) self-hosted in Docker with no external API dependency; (3) simple Python client behind a `VectorStore` Protocol adapter — swapping to OpenSearch (Bedrock) is a one-class change; (4) cosine distance is first-class in Qdrant, no normalization boilerplate. ChromaDB is fine for prototypes but lacks production-grade filtering semantics. FAISS is in-process (no network boundary, no persistence out of the box).

→ [docs/RAG.md §2 — Vector Store](RAG.md#2-vector-store--qdrant)

### 4. How are documents chunked?

Banking KB uses blank-line paragraph splitting (`text.split("\n\n")`). Heading-only paragraphs (single `#` line) are dropped as content-free. The corpus is 8 PT-BR markdown documents — already structured as FAQ-style short paragraphs, so fixed-size chunking would split logically complete answers and create noisy overlap. Each chunk carries `chunk_idx` metadata and a deterministic UUID keyed on `{filename}:{chunk_idx}` for reproducible ingest. Ingestion script: `scripts/ingest_banking_kb.py` — `_split_paragraphs` (lines 27–43).

→ [docs/RAG.md §1 — Chunking Strategy](RAG.md#1-chunking-strategy)

### 5. What retrieval strategy is used?

Dense retrieval with a score threshold and a cross-encoder reranker. Pipeline: `encode query → Qdrant cosine top-20 → score_threshold=0.82 filter → CE reranker → top-3 chunks → LLM`. The threshold (0.82) achieves 65% off-topic rejection with zero in-domain recall cost (recall@3 stays 0.6756). The reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) adds **+1.2pp recall@3, +10.3pp MRR@10, +12.4pp nDCG@10** over the dense baseline. The ranking improvement (MRR/nDCG) is the primary rationale; the recall@3 delta is modest and stated plainly.

→ [docs/RAG.md §4 — Retrieval Strategy](RAG.md#4-retrieval-strategy)

---

## Follow-up Questions

### Why not hybrid retrieval (BM25 + dense)?

Hybrid retrieval (sparse BM25 + dense fusion) was scoped and deferred. Dense retrieval misses exact-keyword / OOV terms — account numbers, product codes, niche regulatory identifiers — where BM25 would win. This is a known confirmed gap (see `LIMITATIONS.md` — "Cut features"). It was cut because: (1) faq_bacen is a natural-language FAQ where paraphrase recall matters more than exact-keyword matching; (2) implementing BM25 fusion adds a pipeline branch + hyperparameter (`alpha`) requiring a dedicated sweep; (3) the `--hybrid` flag is already stubbed in `scripts/eval_retrieval.py` and marked `argparse.SUPPRESS` — it's the next eval iteration, not a design dead-end. In production over a real banking KB with product codes, hybrid is the right call.

### Why enable the reranker if recall@3 gain is only +1.2pp?

The honest answer: +1.2pp recall@3 alone would not justify the latency cost. The actual rationale is **+10.3pp MRR@10 and +12.4pp nDCG@10** — which means the most relevant chunk is ranked first much more reliably. For a chatbot that passes top-3 chunks to the LLM, the position of the best chunk matters: a reranker that puts the best answer first reduces hallucination risk and improves response quality, even when recall@3 is unchanged. Per building-rigorously §7, the recall delta is stated plainly rather than over-claimed.

→ [docs/RAG.md §4 — Reranker before/after](RAG.md#reranker--before--after)

### How did you evaluate? What's the leakage story?

Two datasets with different leakage profiles:

**faq_bacen** (373 queries, 1678 docs) — a frozen Hugging Face public FAQ; eval split is independent of corpus Q/A pairs. Classified as "external-ish." This is where the bake-off and retrieval numbers come from.

**banking_kb** (8 docs) — synthetic, closed-loop: the corpus and its eval queries were authored by the same agent. Used only as an anti-regression gate (did model swap break anything?), not as a primary eval. Absolute recall numbers from banking_kb do not transfer to production — stated explicitly in `LIMITATIONS.md`.

**Anti-tautology gate**: `run_eval_manual` (numpy cosine, independent code path) and `InformationRetrievalEvaluator` (sentence-transformers) produce identical recall@3 = 0.6756 on the faq_bacen dense baseline. This rules out the manual eval path being self-referential (building-rigorously §3).

→ [docs/RAG.md §5 — Eval Methodology](RAG.md#5-eval-methodology-and-leakage-declaration)
