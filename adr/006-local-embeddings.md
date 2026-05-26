# ADR-006: Local Embeddings (sentence-transformers E5)

## Status

Accepted (2026-05-25)

## Context

Voyage AI (`voyage-3`) requires an API key and quota on the critical demo path. A quota exhaustion or network issue during the 8-minute live demo would be catastrophic. The project already carries ~1.5GB of model weights (DeBERTa, detoxify), so an additional 120MB embedding model is marginal.

## Decision

Use `sentence-transformers` with `intfloat/multilingual-e5-small` (~120MB, CPU). Prefix handling (`query:` for questions, `passage:` for documents) is hidden inside the embedding adapter so callers do not need to know about the model's prefix convention.

## Consequences

**Positive:**
- Demo works offline; no API quota risk.
- No external latency or rate-limit variability.
- One less secret to manage (`VOYAGE_API_KEY`).

**Negative:**
- Lower PT-BR retrieval quality than Voyage-3, which was designed for multilingual semantic search.
- ~120MB container image overhead.
- CPU inference adds ~50–100ms to retrieval latency.

**Neutral:**
- Voyage AI remains a planned Extras item with an ADR documenting the quality trade-off; the provider adapter makes the swap one line.
