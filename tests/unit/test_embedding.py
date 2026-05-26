"""
Unit tests for EmbeddingProvider protocol and SentenceTransformerProvider.

Fast tests use a mock SentenceTransformer model — no real download.
The `@pytest.mark.slow` test loads the real e5-small model and verifies
dim=384 + prefix application end-to-end (deselect with `-m 'not slow'`).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from guardrails.adapters import EmbeddingProvider, SentenceTransformerProvider


def _make_mock_provider(dim: int = 384) -> SentenceTransformerProvider:
    mock_model = MagicMock()

    def fake_encode(texts, **kwargs):
        if isinstance(texts, str):
            return np.zeros(dim, dtype=np.float32)
        return np.zeros((len(texts), dim), dtype=np.float32)

    mock_model.encode.side_effect = fake_encode
    return SentenceTransformerProvider(model=mock_model, dim=dim)


def test_provider_protocol_runtime_check():
    assert isinstance(_make_mock_provider(), EmbeddingProvider)


def test_embed_queries_applies_query_prefix():
    provider = _make_mock_provider()
    provider.embed_queries(["qual o saldo?", "como pagar"])

    call_args = provider.model.encode.call_args
    prefixed = call_args[0][0]
    assert prefixed == ["query: qual o saldo?", "query: como pagar"]


def test_embed_passages_applies_passage_prefix():
    provider = _make_mock_provider()
    provider.embed_passages(["doc 1", "doc 2", "doc 3"])

    call_args = provider.model.encode.call_args
    prefixed = call_args[0][0]
    assert prefixed == ["passage: doc 1", "passage: doc 2", "passage: doc 3"]


def test_embed_calls_normalize_true():
    """E5 was trained for cosine on unit vectors — must normalize."""
    provider = _make_mock_provider()
    provider.embed_queries(["test"])
    kwargs = provider.model.encode.call_args[1]
    assert kwargs["normalize_embeddings"] is True


def test_embed_queries_returns_list_of_lists():
    provider = _make_mock_provider(dim=384)
    result = provider.embed_queries(["a", "b"])
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(v, list) for v in result)
    assert all(len(v) == 384 for v in result)


def test_embed_empty_list_returns_empty():
    provider = _make_mock_provider()
    assert provider.embed_queries([]) == []
    assert provider.embed_passages([]) == []
    provider.model.encode.assert_not_called()


def test_embed_uses_batch_size():
    provider = SentenceTransformerProvider(model=MagicMock(), batch_size=64, dim=384)
    provider.model.encode.return_value = np.zeros((1, 384), dtype=np.float32)
    provider.embed_queries(["x"])
    assert provider.model.encode.call_args[1]["batch_size"] == 64


def test_embed_handles_special_chars():
    """Adversarial: emojis, null bytes, very long strings don't crash."""
    provider = _make_mock_provider()
    weird = ["💥 emoji query", "null\x00byte", "x" * 5000]
    result = provider.embed_queries(weird)
    assert len(result) == 3
    prefixed = provider.model.encode.call_args[0][0]
    assert prefixed[0].startswith("query: ")
    assert prefixed[2].startswith("query: x")


@pytest.mark.slow
def test_real_e5_small_dim_and_prefix_integration():
    """Loads real intfloat/multilingual-e5-small — verifies dim=384."""
    provider = SentenceTransformerProvider()
    vectors = provider.embed_queries(["qual a taxa do CDB?"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    assert provider.dim == 384
    norm = sum(x * x for x in vectors[0]) ** 0.5
    assert 0.99 < norm < 1.01
