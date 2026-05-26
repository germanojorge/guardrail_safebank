"""
EmbeddingProvider protocol and SentenceTransformerProvider implementation.

E5 models require literal `"query: "` and `"passage: "` prefixes — recall
drops ~20-30% without them. The provider applies prefixes internally so the
caller stays model-agnostic.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

DEFAULT_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_DIM = 384


@runtime_checkable
class EmbeddingProvider(Protocol):
    dim: int

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerProvider:
    def __init__(
        self,
        model: Any = None,
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
        batch_size: int = 32,
        dim: int = DEFAULT_DIM,
    ) -> None:
        self.model = (
            model if model is not None else self._create_model(model_name, device)
        )
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.dim = dim

    @staticmethod
    def _create_model(model_name: str, device: str) -> Any:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, device=device)

    def _encode(self, prefixed_texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            prefixed_texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode([f"query: {t}" for t in texts])

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode([f"passage: {t}" for t in texts])
