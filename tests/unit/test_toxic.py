"""
Unit tests for ToxicValidator and Validator protocol.

Heavy tests (loading real Detoxify model) are gated behind @pytest.mark.slow
and also respects SKIP_HEAVY_TESTS env var for CI environments where model
download is undesirable.
"""

import os

import pytest
from unittest.mock import MagicMock

from guardrails.validators import ToxicValidator, Validator, ValidatorResult
from tests.fixtures.hatebr_samples import BENIGN_SAMPLES, TOXIC_SAMPLES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_model():
    """Load Detoxify('multilingual') once per test session."""
    from detoxify import Detoxify

    return Detoxify("multilingual")


@pytest.fixture(scope="module")
def toxic_validator(real_model):
    return ToxicValidator(threshold=0.7, model=real_model)


def _make_mock_validator(max_score: float) -> ToxicValidator:
    """Return a ToxicValidator backed by a mock model returning max_score on toxicity."""
    mock_model = MagicMock()
    mock_model.predict.return_value = {
        "toxicity": max_score,
        "severe_toxicity": 0.0,
        "obscene": 0.0,
        "threat": 0.0,
        "insult": 0.0,
    }
    return ToxicValidator(threshold=0.7, model=mock_model)


# ---------------------------------------------------------------------------
# AC #4 — Validator Protocol runtime check
# ---------------------------------------------------------------------------


def test_validator_protocol_runtime_check():
    """ToxicValidator satisfies the Validator Protocol at runtime."""
    validator = _make_mock_validator(max_score=0.0)
    assert isinstance(validator, Validator)


# ---------------------------------------------------------------------------
# ValidatorResult dataclass shape
# ---------------------------------------------------------------------------


def test_result_dataclass_shape():
    """ValidatorResult has correct defaults for optional fields."""
    r = ValidatorResult(passed=True, category="toxicity")
    assert r.score is None
    assert r.details == {}
    assert r.latency_ms is None
    assert r.passed is True
    assert r.category == "toxicity"


# ---------------------------------------------------------------------------
# Happy path — benign inputs pass
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping Detoxify model tests",
)
def test_benign_input_passes(toxic_validator):
    """Benign PT-BR prompts pass the toxicity validator."""
    for text in BENIGN_SAMPLES:
        result = toxic_validator.run(text)
        assert result.passed is True, f"Expected pass for: {text!r}"
        assert result.category == "toxicity"
        assert result.score is not None
        assert result.score < 0.7
        assert result.latency_ms is not None


# ---------------------------------------------------------------------------
# Fail path — HateBR toxic samples are blocked (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping Detoxify model tests",
)
@pytest.mark.parametrize("row_id,text", TOXIC_SAMPLES)
def test_toxic_input_blocks(toxic_validator, row_id, text):
    """HateBR hate speech samples (pre-screened) are blocked by ToxicValidator."""
    result = toxic_validator.run(text)
    assert result.passed is False, f"Expected block for row_id={row_id}: {text!r}"
    assert result.score is not None
    assert result.score > 0.7, (
        f"Expected score > 0.7 for row_id={row_id}, got {result.score}"
    )
    assert "top_category" in result.details
    assert "subscores" in result.details
    assert result.details["subscores"]["toxicity"] >= 0
