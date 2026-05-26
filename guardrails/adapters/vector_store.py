"""
VectorStore protocol, QdrantStore implementation, and InMemoryVectorStore fake.

QdrantStore connects lazily so the API lifespan does not fail when the Qdrant
container is unreachable — `/health` can degrade to `qdrant_reachable=false`
and `/chat` falls back to an empty retrieval result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6333
DEFAULT_COLLECTION = "banking_kb"


@dataclass(frozen=True)
class SearchHit:
    id: str | int
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    def start_collection(self, dim: int, distance: str = "cosine") -> None: ...

    def upsert(self, items: list[tuple[str | int, list[float], dict[str, Any]]]) -> None: ...

    def search(self, query_vector: list[float], top_k: int = 3) -> list[SearchHit]: ...

    def is_reachable(self) -> bool: ...


class QdrantStore:
    def __init__(
        self,
        client: Any = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        collection: str = DEFAULT_COLLECTION,
    ) -> None:
        self._client = client
        self.host = host
        self.port = port
        self.collection = collection

    @staticmethod
    def _create_client(host: str, port: int) -> Any:
        from qdrant_client import QdrantClient

        return QdrantClient(host=host, port=port)

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._create_client(self.host, self.port)
        return self._client

    def is_reachable(self) -> bool:
        try:
            self._ensure_client().get_collections()
            return True
        except Exception:
            return False

    def start_collection(self, dim: int, distance: str = "cosine") -> None:
        from qdrant_client import models

        client = self._ensure_client()
        if client.collection_exists(self.collection):
            return
        distance_map = {
            "cosine": models.Distance.COSINE,
            "dot": models.Distance.DOT,
            "euclid": models.Distance.EUCLID,
        }
        client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=dim,
                distance=distance_map[distance.lower()],
            ),
        )

    def upsert(self, items: list[tuple[str | int, list[float], dict[str, Any]]]) -> None:
        if not items:
            return
        from qdrant_client.models import PointStruct

        points = [PointStruct(id=item_id, vector=vector, payload=payload) for item_id, vector, payload in items]
        self._ensure_client().upsert(collection_name=self.collection, points=points)

    def search(self, query_vector: list[float], top_k: int = 3) -> list[SearchHit]:
        try:
            result = self._ensure_client().query_points(
                collection_name=self.collection,
                query=query_vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception:
            return []
        hits: list[SearchHit] = []
        for point in result.points:
            payload = point.payload or {}
            hits.append(
                SearchHit(
                    id=point.id,
                    score=float(point.score),
                    text=str(payload.get("text", "")),
                    metadata=payload,
                )
            )
        return hits


class InMemoryVectorStore:
    """In-process fake for pipeline tests. Cosine similarity in pure Python."""

    def __init__(self, collection: str = DEFAULT_COLLECTION) -> None:
        self.collection = collection
        self._points: dict[str | int, tuple[list[float], dict[str, Any]]] = {}
        self._dim: int | None = None

    def is_reachable(self) -> bool:
        return True

    def start_collection(self, dim: int, distance: str = "cosine") -> None:
        self._dim = dim

    def upsert(self, items: list[tuple[str | int, list[float], dict[str, Any]]]) -> None:
        for item_id, vector, payload in items:
            self._points[item_id] = (vector, payload)

    def search(self, query_vector: list[float], top_k: int = 3) -> list[SearchHit]:
        if not self._points:
            return []
        q_norm = math.sqrt(sum(x * x for x in query_vector)) or 1.0
        scored: list[tuple[float, str | int, list[float], dict[str, Any]]] = []
        for pid, (vec, payload) in self._points.items():
            v_norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            dot = sum(a * b for a, b in zip(query_vector, vec))
            score = dot / (q_norm * v_norm)
            scored.append((score, pid, vec, payload))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            SearchHit(
                id=pid,
                score=float(score),
                text=str(payload.get("text", "")),
                metadata=payload,
            )
            for score, pid, _vec, payload in scored[:top_k]
        ]
