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

e5-base improved recall@5 by +9.4pp on faq_bacen at the cost of ~300MB extra model weight and ~30ms extra encoding latency per query.

**Retrieval post-processing (SCRUM-39, 2026-06-12):**

Score threshold and cross-encoder reranker are gated by measurement — only enabled if they show a positive recall@3 delta over the e5-base dense baseline (0.6756).

| Setting | config.yaml key | Default |
|---------|-----------------|---------|
| Score threshold | `retrieval.score_threshold` | `null` (disabled) |
| Reranker | `retrieval.reranker.enabled` | `false` |
| Reranker model | `retrieval.reranker.model` | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` |
| Dense candidate pool | `retrieval.top_n` | `20` |

Measurements and final values are recorded in `models/eval/retrieval_before_after.md`.

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
