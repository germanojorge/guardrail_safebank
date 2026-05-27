"""TestClient fixtures for the FastAPI guardrails API.

All fixtures use mock validators — no real Anthropic/ML calls in CI.
Patches `guardrails.api.app._create_components` to return pre-built mock graphs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import sys

import guardrails.api.app  # ensure module is in sys.modules
import guardrails.config
from guardrails.api.app import create_app
from guardrails.pipeline.graph import build_graph
from guardrails.validators.base import ValidatorResult


# ---------------------------------------------------------------------------
# Helpers (mirrored from tests/unit/test_pipeline.py)
# ---------------------------------------------------------------------------


def _passing_result(category: str = "toxicity") -> ValidatorResult:
    return ValidatorResult(passed=True, category=category, score=None, details={}, latency_ms=1.0)


def _failing_result(category: str, details: dict | None = None) -> ValidatorResult:
    return ValidatorResult(
        passed=False,
        category=category,
        score=1.0,
        details=details or {},
        latency_ms=1.0,
    )


def _make_mock_validator(passed: bool = True, category: str = "toxicity", details: dict | None = None) -> MagicMock:
    v = MagicMock()
    v.name = category
    v.run.return_value = _passing_result(category) if passed else _failing_result(category, details)
    return v


def _make_mock_provider(response: str = "Olá! Como posso ajudar?") -> MagicMock:
    p = MagicMock()
    p.complete.return_value = response
    p.client = MagicMock()
    return p


def _make_mock_embedding(dim: int = 384) -> MagicMock:
    e = MagicMock()
    e.dim = dim
    e.model = MagicMock()
    e.embed_queries.side_effect = lambda texts: [[0.0] * dim for _ in texts]
    e.embed_passages.side_effect = lambda texts: [[0.0] * dim for _ in texts]
    return e


def _make_mock_vector_store(reachable: bool = True) -> MagicMock:
    from guardrails.adapters import SearchHit

    s = MagicMock()
    s.is_reachable.return_value = reachable
    s.search.return_value = [
        SearchHit(id="m1", score=0.9, text="mock chunk 1", metadata={}),
        SearchHit(id="m2", score=0.8, text="mock chunk 2", metadata={}),
    ]
    return s


def _build_mock_components(
    *,
    toxic_passes: bool = True,
    pii_input_passes: bool = True,
    pii_output_passes: bool = True,
    jailbreak_passes: bool = True,
    compliance_passes: bool = True,
    compliance_details: dict | None = None,
    pii_input_details: dict | None = None,
    llm_response: str = "Olá! Como posso ajudar?",
):
    mock_toxic = _make_mock_validator(toxic_passes, "toxicity")
    mock_toxic._model = MagicMock()

    mock_pii_input = _make_mock_validator(pii_input_passes, "pii_input", pii_input_details)
    mock_pii_output = _make_mock_validator(pii_output_passes, "pii_output")

    mock_jailbreak = _make_mock_validator(jailbreak_passes, "jailbreak")
    mock_jailbreak._pipeline = MagicMock()

    mock_compliance = _make_mock_validator(compliance_passes, "compliance", compliance_details)
    mock_compliance.client = MagicMock()

    mock_llm = _make_mock_provider(llm_response)
    mock_embedding = _make_mock_embedding()
    mock_vector_store = _make_mock_vector_store()

    graph = build_graph(
        toxic=mock_toxic,
        pii_input=mock_pii_input,
        pii_output=mock_pii_output,
        jailbreak=mock_jailbreak,
        compliance=mock_compliance,
        llm_provider=mock_llm,
        embedding=mock_embedding,
        vector_store=mock_vector_store,
    )
    return (
        graph,
        mock_toxic,
        mock_pii_input,
        mock_jailbreak,
        mock_compliance,
        mock_llm,
        mock_embedding,
        mock_vector_store,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_client(monkeypatch):
    """Factory fixture — call with keyword args to customise validator behaviour."""

    def factory(**kwargs):
        components = _build_mock_components(**kwargs)
        monkeypatch.setattr(guardrails.config, "_config_cache", None)
        monkeypatch.setattr(
            sys.modules["guardrails.api.app"],
            "_create_components",
            lambda cfg: components,
        )
        return create_app()

    return factory


@pytest.fixture
def client(make_client):
    with TestClient(make_client()) as tc:
        yield tc
