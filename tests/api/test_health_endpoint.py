"""Tests for GET /health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_validators_loaded(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ok"

    validators = body["validators_loaded"]
    assert isinstance(validators, list)
    assert len(validators) == 5
    for name in ("toxic", "pii_input", "pii_output", "jailbreak", "compliance"):
        assert name in validators

    ml = body["models_loaded"]
    assert set(ml.keys()) == {
        "detoxify",
        "deberta",
        "anthropic_judge",
        "anthropic_chat",
        "embedding",
        "qdrant_reachable",
    }
    for v in ml.values():
        assert isinstance(v, bool)


def test_health_models_loaded_reflects_state(make_client):
    app = make_client()
    with TestClient(app) as tc:
        resp = tc.get("/health")

    assert resp.status_code == 200
    ml = resp.json()["models_loaded"]
    # conftest sets _model, _pipeline, compliance.client, llm.client as MagicMock (truthy)
    assert ml["detoxify"] is True
    assert ml["deberta"] is True
    assert ml["anthropic_judge"] is True
    assert ml["anthropic_chat"] is True
    assert ml["embedding"] is True
    assert ml["qdrant_reachable"] is True


def test_health_models_loaded_false_when_none(make_client, monkeypatch):
    """Models with None attrs should surface as False in /health."""
    import sys

    from tests.api.conftest import _build_mock_components

    components = list(_build_mock_components())
    graph, toxic, jailbreak, compliance, llm, embedding, vector_store = components
    toxic._model = None
    jailbreak._pipeline = None
    embedding.model = None
    vector_store.is_reachable.return_value = False

    monkeypatch.setattr(
        sys.modules["guardrails.api.app"],
        "_create_components",
        lambda cfg: (graph, toxic, jailbreak, compliance, llm, embedding, vector_store),
    )
    import guardrails.config

    monkeypatch.setattr(guardrails.config, "_config_cache", None)

    from guardrails.api.app import create_app

    app_instance = create_app()
    with TestClient(app_instance) as tc:
        resp = tc.get("/health")

    ml = resp.json()["models_loaded"]
    assert ml["detoxify"] is False
    assert ml["deberta"] is False
    assert ml["anthropic_judge"] is True
    assert ml["anthropic_chat"] is True
    assert ml["embedding"] is False
    assert ml["qdrant_reachable"] is False
