"""
Reranker Protocol and implementations for cross-encoder reranking.

CrossEncoderReranker retrieves top-N dense candidates and reranks them
with a cross-encoder model, returning top_k in descending score order.
IdentityReranker is a deterministic fake for tests (returns hits[:top_k] unchanged).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from guardrails.adapters.vector_store import SearchHit

DEFAULT_RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


@runtime_checkable
class Reranker(Protocol):
    """Cross-encoder reranker.

    Scores (query, passage) pairs with a cross-encoder and returns
    top_k SearchHits in descending cross-encoder score order.
    """

    def rerank(self, query: str, hits: list[SearchHit], top_k: int = 3) -> list[SearchHit]: ...


class CrossEncoderReranker:
    """Sentence-transformers CrossEncoder reranker.

    The model is lazily loaded on first call and can be injected for
    testing without triggering an expensive download.
    """

    def __init__(
        self,
        model: Any = None,
        model_name: str = DEFAULT_RERANKER_MODEL,
        device: str = "cpu",
    ) -> None:
        self.model = model if model is not None else self._create_model(model_name, device)
        self.model_name = model_name
        self.device = device

    @staticmethod
    def _create_model(model_name: str, device: str) -> Any:
        from sentence_transformers import CrossEncoder

        return CrossEncoder(model_name, device=device)

    def rerank(self, query: str, hits: list[SearchHit], top_k: int = 3) -> list[SearchHit]:
        if not hits:
            return []
        pairs = [(query, h.text) for h in hits]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(scores, hits), key=lambda t: t[0], reverse=True)
        return [SearchHit(id=h.id, score=float(s), text=h.text, metadata=h.metadata) for s, h in ranked[:top_k]]


class IdentityReranker:
    """Deterministic no-op reranker for tests.

    Returns hits[:top_k] in original order (preserves bi-encoder ordering).
    """

    def rerank(self, query: str, hits: list[SearchHit], top_k: int = 3) -> list[SearchHit]:
        return list(hits[:top_k])
