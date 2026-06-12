# ADR-006: Local Embeddings (sentence-transformers E5)

## Status

Updated (2026-06-12): e5-small → e5-base after SCRUM-38 bake-off; score threshold + cross-encoder reranker gated by SCRUM-39 measurements.

## Context

Voyage AI (`voyage-3`) requires an API key and quota on the critical demo path. A quota exhaustion or network issue during the 8-minute live demo would be catastrophic. The project already carries ~1.5GB of model weights (DeBERTa, detoxify), so an additional embedding model is marginal.

## Decision

Use `sentence-transformers` locally (CPU). Prefix handling (`query:` for questions, `passage:` for documents) is hidden inside the embedding adapter so callers do not need to know about the model's prefix convention.

**Model history (SCRUM-38 bake-off, 2026-06-11):**

| Model | Size | faq_bacen recall@5 | banking_kb recall@5 | Decision |
|-------|------|--------------------|---------------------|----------|
| `intfloat/multilingual-e5-small` | ~120MB | 0.6836 | 0.8750 | superseded |
| `intfloat/multilingual-e5-base` | ~420MB | **0.7480** | **0.9375** | **current** |

e5-base improved recall@5 by +6.4pp on faq_bacen (0.6836 → 0.7480, `models/eval/bakeoff_faq_bacen_summary.json`) at the cost of ~300MB extra model weight and ~32ms extra CPU encoding latency per query (22.7 → 55.2 ms).

**Retrieval post-processing (SCRUM-39, 2026-06-12):**

Score threshold and cross-encoder reranker were gated by measurement (SCRUM-39, 2026-06-12). Both showed positive deltas and are **enabled** in the shipped config.

| Setting | config.yaml key | Shipped value | Measured delta |
|---------|-----------------|---------------|----------------|
| Score threshold | `retrieval.score_threshold` | **`0.82`** | 65% off-topic rejection, 0 recall@3 cost |
| Reranker | `retrieval.reranker.enabled` | **`true`** | +1.2pp recall@3, +10.3pp MRR@10, +12.4pp nDCG@10 |
| Reranker model | `retrieval.reranker.model` | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | — |
| Dense candidate pool | `retrieval.top_n` | `20` | — |

Full before/after data and threshold sweep: `models/eval/retrieval_before_after.md`.

## Consequences

**Positive:**
- Demo works offline; no API quota risk.
- No external latency or rate-limit variability.
- One less secret to manage (`VOYAGE_API_KEY`).
- e5-base gives materially better PT-BR recall than e5-small.

**Negative:**
- e5-base is ~300MB heavier than e5-small (~420MB vs ~120MB).
- CPU inference adds ~50–100ms to retrieval latency per query.
- Cross-encoder reranker (if enabled) adds ~200–500ms additional latency.

**Neutral:**
- Voyage AI remains a planned Extras item; the provider adapter makes the swap one line.
- Score threshold and reranker are feature-flagged via `config.yaml` — no code change needed to toggle.
