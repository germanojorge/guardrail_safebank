"""
Unit tests for VectorStore protocol, QdrantStore, and InMemoryVectorStore.

QdrantStore tests use a mocked qdrant_client — no live container needed.
InMemoryVectorStore is exercised end-to-end since it's pure Python.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from guardrails.adapters import (
    InMemoryVectorStore,
    QdrantStore,
    SearchHit,
    VectorStore,
)


def _make_qdrant_store(reachable: bool = True) -> QdrantStore:
    mock_client = MagicMock()
    mock_client.collection_exists.return_value = False
    if not reachable:
        mock_client.get_collections.side_effect = ConnectionError("qdrant down")
    return QdrantStore(client=mock_client, collection="test_kb")


def test_qdrant_protocol_runtime_check():
    assert isinstance(_make_qdrant_store(), VectorStore)


def test_in_memory_protocol_runtime_check():
    assert isinstance(InMemoryVectorStore(), VectorStore)


def test_start_collection_creates_when_missing():
    store = _make_qdrant_store()
    store.start_collection(dim=384, distance="cosine")
    store._client.create_collection.assert_called_once()
    kwargs = store._client.create_collection.call_args[1]
    assert kwargs["collection_name"] == "test_kb"
    assert kwargs["vectors_config"].size == 384


def test_start_collection_idempotent():
    store = _make_qdrant_store()
    store._client.collection_exists.return_value = True
    store.start_collection(dim=384)
    store._client.create_collection.assert_not_called()


def test_ensure_collection_recreates_on_dim_mismatch():
    store = _make_qdrant_store()
    store._client.collection_exists.return_value = True
    mock_vectors = MagicMock()
    mock_vectors.size = 384
    mock_info = MagicMock()
    mock_info.config.params.vectors = mock_vectors
    store._client.get_collection.return_value = mock_info

    store.ensure_collection(dim=768, distance="cosine")

    store._client.delete_collection.assert_called_once_with("test_kb")
    store._client.create_collection.assert_called_once()
    assert store._client.create_collection.call_args[1]["vectors_config"].size == 768


def test_ensure_collection_skips_when_dim_matches():
    store = _make_qdrant_store()
    store._client.collection_exists.return_value = True
    mock_vectors = MagicMock()
    mock_vectors.size = 768
    mock_info = MagicMock()
    mock_info.config.params.vectors = mock_vectors
    store._client.get_collection.return_value = mock_info

    store.ensure_collection(dim=768, distance="cosine")

    store._client.delete_collection.assert_not_called()
    store._client.create_collection.assert_not_called()


def test_upsert_builds_pointstruct():
    store = _make_qdrant_store()
    items = [
        (1, [0.1, 0.2, 0.3], {"text": "doc 1", "source": "faq.md"}),
        (2, [0.4, 0.5, 0.6], {"text": "doc 2", "source": "tos.md"}),
    ]
    store.upsert(items)

    store._client.upsert.assert_called_once()
    call_kwargs = store._client.upsert.call_args[1]
    assert call_kwargs["collection_name"] == "test_kb"
    points = call_kwargs["points"]
    assert len(points) == 2
    assert points[0].id == 1
    assert points[0].vector == [0.1, 0.2, 0.3]
    assert points[0].payload["text"] == "doc 1"


def test_upsert_empty_is_noop():
    store = _make_qdrant_store()
    store.upsert([])
    store._client.upsert.assert_not_called()


def test_search_returns_searchhits_with_text():
    store = _make_qdrant_store()
    mock_point_a = MagicMock(id="a", score=0.95, payload={"text": "hit A", "source": "x"})
    mock_point_b = MagicMock(id="b", score=0.85, payload={"text": "hit B"})
    mock_result = MagicMock()
    mock_result.points = [mock_point_a, mock_point_b]
    store._client.query_points.return_value = mock_result

    hits = store.search([0.1, 0.2, 0.3], top_k=2)

    assert len(hits) == 2
    assert all(isinstance(h, SearchHit) for h in hits)
    assert hits[0].id == "a"
    assert hits[0].score == 0.95
    assert hits[0].text == "hit A"
    assert hits[0].metadata == {"text": "hit A", "source": "x"}
    assert hits[1].text == "hit B"


def test_search_passes_top_k():
    store = _make_qdrant_store()
    mock_result = MagicMock()
    mock_result.points = []
    store._client.query_points.return_value = mock_result

    store.search([0.0, 0.0, 0.0], top_k=5)
    kwargs = store._client.query_points.call_args[1]
    assert kwargs["limit"] == 5


def test_search_failure_returns_empty_list():
    """Qdrant down → search degrades to empty, not exception."""
    store = _make_qdrant_store()
    store._client.query_points.side_effect = ConnectionError("qdrant down")
    assert store.search([0.0], top_k=3) == []


def test_is_reachable_true_when_client_responds():
    store = _make_qdrant_store(reachable=True)
    assert store.is_reachable() is True


def test_is_reachable_false_when_client_errors():
    store = _make_qdrant_store(reachable=False)
    assert store.is_reachable() is False


def test_in_memory_search_orders_by_cosine_score():
    store = InMemoryVectorStore()
    store.start_collection(dim=4)
    store.upsert(
        [
            ("a", [1.0, 0.0, 0.0, 0.0], {"text": "closest"}),
            ("b", [0.0, 1.0, 0.0, 0.0], {"text": "orthogonal"}),
            ("c", [-1.0, 0.0, 0.0, 0.0], {"text": "opposite"}),
        ]
    )
    hits = store.search([1.0, 0.1, 0.0, 0.0], top_k=2)
    assert len(hits) == 2
    assert hits[0].id == "a"
    assert hits[0].score > hits[1].score


def test_in_memory_empty_returns_empty():
    store = InMemoryVectorStore()
    store.start_collection(dim=4)
    assert store.search([1.0, 0.0, 0.0, 0.0], top_k=3) == []


# ---------------------------------------------------------------------------
# score_threshold — InMemoryVectorStore
# ---------------------------------------------------------------------------


def test_in_memory_score_threshold_drops_low_scores():
    store = InMemoryVectorStore()
    store.start_collection(dim=4)
    store.upsert(
        [
            ("high", [1.0, 0.0, 0.0, 0.0], {"text": "high score"}),
            ("low", [0.0, 0.0, 1.0, 0.0], {"text": "low score"}),  # orthogonal to query → score ≈ 0
        ]
    )
    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=3, score_threshold=0.5)
    ids = [h.id for h in hits]
    assert "high" in ids
    assert "low" not in ids


def test_in_memory_score_threshold_none_returns_all():
    store = InMemoryVectorStore()
    store.start_collection(dim=4)
    store.upsert(
        [
            ("a", [1.0, 0.0, 0.0, 0.0], {"text": "a"}),
            ("b", [0.1, 0.0, 0.0, 0.0], {"text": "b"}),
        ]
    )
    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=3, score_threshold=None)
    assert len(hits) == 2


def test_in_memory_high_threshold_returns_empty():
    store = InMemoryVectorStore()
    store.start_collection(dim=4)
    store.upsert([("a", [0.5, 0.5, 0.0, 0.0], {"text": "a"})])
    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=3, score_threshold=0.99)
    assert hits == []


# ---------------------------------------------------------------------------
# score_threshold — QdrantStore (mocked client)
# ---------------------------------------------------------------------------


def test_qdrant_passes_score_threshold_to_query_points():
    store = _make_qdrant_store()
    mock_result = MagicMock()
    mock_result.points = []
    store._client.query_points.return_value = mock_result

    store.search([0.1, 0.2, 0.3], top_k=5, score_threshold=0.75)
    kwargs = store._client.query_points.call_args[1]
    assert kwargs.get("score_threshold") == 0.75


def test_qdrant_no_score_threshold_kwarg_when_none():
    store = _make_qdrant_store()
    mock_result = MagicMock()
    mock_result.points = []
    store._client.query_points.return_value = mock_result

    store.search([0.1, 0.2, 0.3], top_k=5, score_threshold=None)
    kwargs = store._client.query_points.call_args[1]
    assert "score_threshold" not in kwargs
