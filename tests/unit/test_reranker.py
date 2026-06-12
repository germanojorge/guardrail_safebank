"""Unit tests for Reranker Protocol, CrossEncoderReranker, and IdentityReranker.

All tests are fast — no real model downloads.
CrossEncoderReranker is exercised via an injected MagicMock CrossEncoder.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from guardrails.adapters import (
    CrossEncoderReranker,
    IdentityReranker,
    Reranker,
    SearchHit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hits(n: int) -> list[SearchHit]:
    return [SearchHit(id=f"doc_{i}", score=float(n - i) / n, text=f"text {i}") for i in range(n)]


def _make_mock_cross_encoder(scores: list[float]) -> MagicMock:
    """Return a CrossEncoder mock whose predict() returns the given scores."""
    model = MagicMock()
    model.predict.return_value = np.array(scores)
    return model


# ---------------------------------------------------------------------------
# Protocol runtime checks
# ---------------------------------------------------------------------------


def test_identity_reranker_is_reranker():
    assert isinstance(IdentityReranker(), Reranker)


def test_cross_encoder_reranker_is_reranker():
    mock_model = _make_mock_cross_encoder([0.9])
    assert isinstance(CrossEncoderReranker(model=mock_model), Reranker)


# ---------------------------------------------------------------------------
# IdentityReranker
# ---------------------------------------------------------------------------


def test_identity_reranker_returns_top_k():
    hits = _make_hits(10)
    result = IdentityReranker().rerank("query", hits, top_k=3)
    assert len(result) == 3


def test_identity_reranker_preserves_order():
    hits = _make_hits(5)
    result = IdentityReranker().rerank("query", hits, top_k=3)
    assert [h.id for h in result] == ["doc_0", "doc_1", "doc_2"]


def test_identity_reranker_empty_hits():
    result = IdentityReranker().rerank("query", [], top_k=3)
    assert result == []


def test_identity_reranker_top_k_larger_than_hits():
    hits = _make_hits(2)
    result = IdentityReranker().rerank("query", hits, top_k=5)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# CrossEncoderReranker — mocked model
# ---------------------------------------------------------------------------


def test_cross_encoder_reranks_descending():
    """Lower-scored docs move up after reranking with higher cross-encoder score."""
    hits = _make_hits(3)  # doc_0 (score 1.0), doc_1 (0.67), doc_2 (0.33)
    # Cross-encoder inverts the order: doc_2 best, doc_1 mid, doc_0 worst
    mock_model = _make_mock_cross_encoder([0.1, 0.5, 0.9])
    reranker = CrossEncoderReranker(model=mock_model)

    result = reranker.rerank("q", hits, top_k=3)
    assert [h.id for h in result] == ["doc_2", "doc_1", "doc_0"]


def test_cross_encoder_replaces_score():
    """Returned SearchHits carry the cross-encoder score, not the original cosine."""
    hits = _make_hits(2)
    mock_model = _make_mock_cross_encoder([0.3, 0.8])
    reranker = CrossEncoderReranker(model=mock_model)

    result = reranker.rerank("q", hits, top_k=2)
    scores = [h.score for h in result]
    # Descending: doc_1 (0.8), doc_0 (0.3)
    assert abs(scores[0] - 0.8) < 1e-6
    assert abs(scores[1] - 0.3) < 1e-6


def test_cross_encoder_slices_to_top_k():
    hits = _make_hits(5)
    mock_model = _make_mock_cross_encoder([0.1, 0.9, 0.5, 0.7, 0.3])
    reranker = CrossEncoderReranker(model=mock_model)

    result = reranker.rerank("q", hits, top_k=2)
    assert len(result) == 2
    assert result[0].id == "doc_1"  # score 0.9 — highest


def test_cross_encoder_passes_correct_pairs_to_predict():
    hits = [
        SearchHit(id="a", score=0.5, text="alpha text"),
        SearchHit(id="b", score=0.3, text="beta text"),
    ]
    mock_model = _make_mock_cross_encoder([0.6, 0.4])
    reranker = CrossEncoderReranker(model=mock_model)

    reranker.rerank("my query", hits, top_k=2)

    call_args = mock_model.predict.call_args[0][0]
    assert call_args == [("my query", "alpha text"), ("my query", "beta text")]


def test_cross_encoder_empty_hits():
    mock_model = _make_mock_cross_encoder([])
    reranker = CrossEncoderReranker(model=mock_model)
    result = reranker.rerank("q", [], top_k=3)
    assert result == []
    mock_model.predict.assert_not_called()


def test_cross_encoder_preserves_metadata():
    hits = [SearchHit(id="x", score=0.5, text="t", metadata={"source": "faq"})]
    mock_model = _make_mock_cross_encoder([0.9])
    reranker = CrossEncoderReranker(model=mock_model)

    result = reranker.rerank("q", hits, top_k=1)
    assert result[0].metadata == {"source": "faq"}
