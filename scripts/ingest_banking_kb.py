#!/usr/bin/env python
"""
Ingest the banking knowledge base into Qdrant.

Reads markdown files from data/banking_kb/*.md, splits each by blank-line
paragraphs, embeds with the `passage:` prefix via SentenceTransformerProvider,
and upserts into Qdrant with deterministic UUID5 ids so reruns are idempotent.

Usage:
    docker run -d -p 6333:6333 qdrant/qdrant
    uv run python scripts/ingest_banking_kb.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from guardrails.adapters import QdrantStore, SentenceTransformerProvider
from guardrails.config import get_config

NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
BATCH_SIZE = 32


def _split_paragraphs(text: str) -> list[str]:
    """Split by blank lines, drop heading-only paragraphs.

    A heading-only paragraph is a single line starting with '#'. Multi-line
    blocks that begin with a heading are kept (the heading provides context
    for the body text that follows).
    """
    blocks: list[str] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) == 1 and lines[0].startswith("#"):
            continue
        blocks.append(block)
    return blocks


def _doc_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return fallback


def _load_corpus(corpus_dir: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(corpus_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title = _doc_title(content, fallback=path.stem)
        for idx, paragraph in enumerate(_split_paragraphs(content)):
            point_id = str(uuid.uuid5(NAMESPACE, f"{path.name}:{idx}"))
            items.append(
                {
                    "id": point_id,
                    "text": paragraph,
                    "source": path.name,
                    "title": title,
                    "chunk_idx": idx,
                }
            )
    return items


def main() -> int:
    cfg = get_config()
    emb_cfg = cfg.get("embedding", {})
    qd_cfg = cfg.get("qdrant", {})

    corpus_dir = Path("data/banking_kb")
    if not corpus_dir.exists():
        print(f"[ERROR] corpus dir not found: {corpus_dir}", file=sys.stderr)
        return 1

    items = _load_corpus(corpus_dir)
    if not items:
        print(f"[ERROR] no .md files found in {corpus_dir}", file=sys.stderr)
        return 1

    print(
        f"[ingest] loaded {len(items)} chunks from "
        f"{len(set(i['source'] for i in items))} documents"
    )

    embedding = SentenceTransformerProvider(
        model_name=emb_cfg.get("model", "intfloat/multilingual-e5-small"),
        device=emb_cfg.get("device", "cpu"),
        batch_size=BATCH_SIZE,
    )
    print(f"[ingest] embedding model loaded (dim={embedding.dim})")

    texts = [item["text"] for item in items]
    vectors = embedding.embed_passages(texts)

    store = QdrantStore(
        host=qd_cfg.get("host", "localhost"),
        port=qd_cfg.get("port", 6333),
        collection=qd_cfg.get("collection", "banking_kb"),
    )
    if not store.is_reachable():
        print(
            f"[ERROR] qdrant unreachable at {store.host}:{store.port}. "
            "Start it with: docker run -d -p 6333:6333 qdrant/qdrant",
            file=sys.stderr,
        )
        return 2

    store.start_collection(dim=embedding.dim, distance="cosine")
    print(f"[ingest] collection '{store.collection}' ready")

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
    print(f"[ingest] upserted {len(payload_items)} points. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
