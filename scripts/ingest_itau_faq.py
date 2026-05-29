#!/usr/bin/env python
"""Ingest do dataset Itau-Unibanco/FAQ_BACEN no Qdrant.

Carrega o dataset público do HF Hub, embeda cada par pergunta+resposta
com intfloat/multilingual-e5-small e upserta na coleção `itau_faq`.
IDs são UUID5 determinísticos (rerun é idempotente).

Usage:
    uv run python scripts/ingest_itau_faq.py
    # ou via docker compose:
    docker compose run --rm ingest_itau
"""

from __future__ import annotations

import sys
import uuid

from guardrails.adapters import QdrantStore, SentenceTransformerProvider
from guardrails.config import get_config

NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
DATASET_NAME = "Itau-Unibanco/FAQ_BACEN"
COLLECTION = "itau_faq"
BATCH_SIZE = 32


def _load_dataset() -> list[dict]:
    try:
        from datasets import load_dataset
    except ImportError:
        print("[ERROR] 'datasets' not installed. Run: uv add datasets", file=sys.stderr)
        sys.exit(1)

    print(f"[ingest] downloading {DATASET_NAME} from HuggingFace Hub...")
    ds = load_dataset(DATASET_NAME, split="train")
    print(f"[ingest] loaded {len(ds)} rows")

    items = []
    for idx, row in enumerate(ds):
        # Tenta campos comuns do dataset; ajusta se necessário
        question = row.get("question") or row.get("pergunta") or row.get("input") or ""
        answer = row.get("answer") or row.get("resposta") or row.get("output") or ""
        text = f"Pergunta: {question}\nResposta: {answer}".strip()
        if not text:
            continue
        point_id = str(uuid.uuid5(NAMESPACE, f"itau_faq:{idx}"))
        items.append(
            {
                "id": point_id,
                "text": text,
                "source": "itau_faq_bacen",
                "title": question[:100] if question else f"item_{idx}",
                "chunk_idx": idx,
            }
        )
    return items


def main() -> int:
    cfg = get_config()
    emb_cfg = cfg.get("embedding", {})
    qd_cfg = cfg.get("qdrant", {})

    items = _load_dataset()
    if not items:
        print("[ERROR] dataset vazio ou campos não encontrados", file=sys.stderr)
        return 1

    print(f"[ingest] {len(items)} chunks preparados")

    embedding = SentenceTransformerProvider(
        model_name=emb_cfg.get("model", "intfloat/multilingual-e5-small"),
        device=emb_cfg.get("device", "cpu"),
        batch_size=BATCH_SIZE,
    )
    print(f"[ingest] embedding model loaded (dim={embedding.dim})")

    texts = [item["text"] for item in items]
    vectors = embedding.embed_passages(texts)

    host = qd_cfg.get("host", "localhost")
    port = qd_cfg.get("port", 6333)
    store = QdrantStore(host=host, port=port, collection=COLLECTION)
    if not store.is_reachable():
        print(
            f"[ERROR] qdrant unreachable at {host}:{port}. Start it with: docker run -d -p 6333:6333 qdrant/qdrant",
            file=sys.stderr,
        )
        return 2

    store.start_collection(dim=embedding.dim, distance="cosine")
    print(f"[ingest] collection '{COLLECTION}' ready")

    payload_items = [
        (
            item["id"],
            vector,
            {
                "text": item["text"],
                "source": item["source"],
                "title": item["title"],
                "chunk_idx": item["chunk_idx"],
            },
        )
        for item, vector in zip(items, vectors)
    ]
    store.upsert(payload_items)
    print(f"[ingest] upserted {len(payload_items)} points into '{COLLECTION}'. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
