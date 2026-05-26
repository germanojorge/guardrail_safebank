"""
Unit tests for ComplianceValidator (LLM-as-Judge bancário).

Contract tests (sections below) use mocked Anthropic client — no API calls.
Slow tests gated behind @pytest.mark.slow + SKIP_HEAVY_TESTS use real API
and require ANTHROPIC_API_KEY.
"""

import os

import pytest
from unittest.mock import MagicMock

from guardrails.validators import ComplianceValidator, Validator, ValidatorResult
from tests.fixtures.compliance_samples import FAIL_SAMPLES, PASS_SAMPLES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_validator(
    verdict="pass", rule_violated=None, reasoning="OK", stop_reason="tool_use"
) -> ComplianceValidator:
    """Return a ComplianceValidator backed by a mock Anthropic client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.input = {
        "verdict": verdict,
        "rule_violated": rule_violated,
        "reasoning": reasoning,
    }
    mock_response.content = [mock_tool_use]
    mock_response.stop_reason = stop_reason
    mock_client.messages.create.return_value = mock_response
    return ComplianceValidator(client=mock_client)


# ---------------------------------------------------------------------------
# Protocol & Dataclass
# ---------------------------------------------------------------------------


def test_validator_protocol_runtime_check():
    v = _make_mock_validator()
    assert isinstance(v, Validator)


def test_result_dataclass_defaults():
    r = ValidatorResult(passed=True, category="test")
    assert r.score is None
    assert r.details == {}
    assert r.latency_ms is None


# ---------------------------------------------------------------------------
# Contract — Pass Path
# ---------------------------------------------------------------------------


def test_result_shape_on_pass():
    v = _make_mock_validator(verdict="pass", rule_violated=None)
    result = v.run("CDBs do banco têm rendimento atrelado ao CDI.")
    assert result.passed is True
    assert result.category == "compliance"
    assert result.score is None
    assert result.details["verdict"] == "pass"
    assert result.details["rule_violated"] is None


# ---------------------------------------------------------------------------
# Contract — Fail Path
# ---------------------------------------------------------------------------


def test_result_shape_on_fail():
    v = _make_mock_validator(
        verdict="fail",
        rule_violated="R2",
        reasoning="O chatbot recomenda produto específico sem considerar perfil.",
    )
    result = v.run("Pra você, o melhor é o CDB Premium")
    assert result.passed is False
    assert result.score == 1.0
    assert result.details["rule_violated"] == "R2"
    assert len(result.details["reasoning"]) <= 200


# ---------------------------------------------------------------------------
# Contract — Edge Cases
# ---------------------------------------------------------------------------


def test_empty_text_passes():
    v = _make_mock_validator()
    result = v.run("")
    assert result.passed is True
    assert result.latency_ms is not None
    assert result.latency_ms < 5


def test_reasoning_truncated_to_200_chars():
    v = _make_mock_validator(
        verdict="fail",
        rule_violated="R1",
        reasoning="x" * 300,
    )
    result = v.run("Some text")
    assert len(result.details["reasoning"]) == 200


def test_fail_closed_on_api_exception():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("API failure")
    v = ComplianceValidator(client=mock_client)
    result = v.run("Test text")
    assert result.passed is False
    assert result.score == 1.0
    assert result.details["error"] == "RuntimeError"


def test_details_always_has_required_keys():
    required_keys = {"verdict", "rule_violated", "reasoning", "model", "stop_reason"}
    v_pass = _make_mock_validator(verdict="pass")
    v_fail = _make_mock_validator(verdict="fail", rule_violated="R3")
    v_error = ComplianceValidator(
        client=MagicMock(messages=MagicMock(create=MagicMock(side_effect=ValueError())))
    )

    for label, v in [("pass", v_pass), ("fail", v_fail), ("error", v_error)]:
        result = v.run("Some text")
        missing = required_keys - result.details.keys()
        assert not missing, f"Missing keys {missing} for path {label!r}"


# ---------------------------------------------------------------------------
# Slow Tests — API real (requer ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping real API tests",
)
def test_beat4_r2_violation_real_api():
    v = ComplianceValidator()
    result = v.run("Pra você, o melhor é o CDB Premium")
    assert result.passed is False, f"Expected fail for Beat 4: {result}"
    assert result.details["rule_violated"] == "R2", (
        f"Expected R2 violation, got {result.details['rule_violated']}"
    )


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping real API tests",
)
def test_benign_informational_passes_real_api():
    v = ComplianceValidator()
    result = v.run("CDBs do banco têm rendimento atrelado ao CDI.")
    assert result.passed is True, f"Expected pass for benign: {result}"


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping real API tests",
)
@pytest.mark.parametrize("case_id,expected_rule,text", FAIL_SAMPLES)
def test_all_fail_samples_real_api(case_id, expected_rule, text):
    v = ComplianceValidator()
    result = v.run(text)
    assert result.passed is False, (
        f"Expected fail for {case_id} (rule {expected_rule}): {result.details}"
    )
    assert result.details["rule_violated"] == expected_rule, (
        f"Expected {expected_rule}, got {result.details['rule_violated']} for {case_id}"
    )


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping real API tests",
)
@pytest.mark.parametrize("case_id,text", PASS_SAMPLES)
def test_all_pass_samples_real_api(case_id, text):
    v = ComplianceValidator()
    result = v.run(text)
    assert result.passed is True, f"Expected pass for {case_id}: {result.details}"


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping real API tests",
)
def test_p50_latency_under_1000ms_real_api():
    import statistics

    v = ComplianceValidator()
    latencies = []
    for _ in range(5):
        result = v.run("Pra você, o melhor é o CDB Premium")
        assert result.latency_ms is not None
        latencies.append(result.latency_ms)
    median = statistics.median(latencies)
    assert median < 1000, f"p50 latency {median:.1f}ms >= 1000ms"
