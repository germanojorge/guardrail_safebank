#!/usr/bin/env python
"""Ingest do dataset Itau-Unibanco/FAQ_BACEN no Qdrant.

Carrega apenas o split ``train`` do HF Hub (split ``test`` fica de fora para
avaliação em ``data/eval/faq_bacen_eval.jsonl``), embeda cada par
pergunta+resposta com o modelo configurado em ``config.yaml`` e upserta na
coleção Qdrant configurada (default ``itau_faq``). IDs são UUID5 determinísticos
(rerun é idempotente). Se a dimensão do embedding mudou (ex.: e5-small→e5-base),
a coleção é recriada automaticamente.

Usage:
    uv run python scripts/ingest_itau_faq.py
    docker compose run --rm ingest
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de importar datasets/transformers

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _faq_data import load_faq_train_for_ingest  # noqa: E402

from guardrails.adapters import QdrantStore, SentenceTransformerProvider
from guardrails.config import get_config

NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
BATCH_SIZE = 32


def _build_items(rows: list[dict[str, str]]) -> list[dict]:
    items = []
    for row in rows:
        question = row["question"]
        answer = row["answer"]
        doc_id = row["doc_id"]
        text = f"Pergunta: {question}\nResposta: {answer}"
        point_id = str(uuid.uuid5(NAMESPACE, f"itau_faq:{doc_id}"))
        items.append(
            {
                "id": point_id,
                "text": text,
                "source": "itau_faq_bacen",
                "title": question[:100],
                "doc_id": doc_id,
                "chunk_idx": int(doc_id.split("_", 1)[1]),
            }
        )
    return items


def main() -> int:
    cfg = get_config()
    emb_cfg = cfg.get("embedding", {})
    qd_cfg = cfg.get("qdrant", {})

    rows = load_faq_train_for_ingest()
    if not rows:
        print("[ERROR] dataset vazio ou campos não encontrados", file=sys.stderr)
        return 1

    items = _build_items(rows)
    print(f"[ingest] {len(items)} chunks preparados (test split reservado para eval)")

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
    collection = qd_cfg.get("collection", "itau_faq")
    store = QdrantStore(host=host, port=port, collection=collection)
    if not store.is_reachable():
        print(
            f"[ERROR] qdrant unreachable at {host}:{port}. Start it with: docker run -d -p 6333:6333 qdrant/qdrant",
            file=sys.stderr,
        )
        return 2

    store.ensure_collection(dim=embedding.dim, distance="cosine")
    print(f"[ingest] collection '{collection}' ready")

    payload_items = [
        (
            item["id"],
            vector,
            {
                "text": item["text"],
                "source": item["source"],
                "title": item["title"],
                "doc_id": item["doc_id"],
                "chunk_idx": item["chunk_idx"],
            },
        )
        for item, vector in zip(items, vectors)
    ]
    store.upsert(payload_items)
    print(f"[ingest] upserted {len(payload_items)} points into '{collection}'. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
