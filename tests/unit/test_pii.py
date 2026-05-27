"""
Unit tests for PIIValidator and Validator protocol.

All tests are fast (regex-only, no model load). None require SKIP_HEAVY_TESTS.
"""

import pytest

from guardrails.validators import PIIValidator, Validator, ValidatorResult
from tests.fixtures.pii_samples import BENIGN_SAMPLES, PII_SAMPLES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def input_validator() -> PIIValidator:
    return PIIValidator(stage="input")


@pytest.fixture
def output_validator() -> PIIValidator:
    return PIIValidator(stage="output")


# ---------------------------------------------------------------------------
# Protocol and dataclass
# ---------------------------------------------------------------------------


def test_validator_protocol_runtime_check():
    """PIIValidator satisfies the Validator Protocol at runtime."""
    assert isinstance(PIIValidator("input"), Validator)


def test_result_dataclass_shape_for_pii(input_validator):
    """ValidatorResult returned for benign text has the correct shape."""
    result = input_validator.run("Olá, como posso ajudar?")
    assert isinstance(result, ValidatorResult)
    assert result.score is None
    assert isinstance(result.details, dict)
    assert result.latency_ms is not None


def test_invalid_stage_raises():
    """PIIValidator("middle") raises ValueError with clear message."""
    with pytest.raises(ValueError, match="stage must be 'input' or 'output'"):
        PIIValidator("middle")


# ---------------------------------------------------------------------------
# Benign pass-path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", BENIGN_SAMPLES)
def test_benign_text_passes_input(text):
    validator = PIIValidator(stage="input")
    result = validator.run(text)
    assert result.passed is True, f"Expected pass for: {text!r}"
    assert result.category == "pii_input"
    assert result.details["entities"] == {}
    assert result.latency_ms is not None


@pytest.mark.parametrize("text", BENIGN_SAMPLES)
def test_benign_text_passes_output(text):
    validator = PIIValidator(stage="output")
    result = validator.run(text)
    assert result.passed is True, f"Expected pass for: {text!r}"
    assert result.category == "pii_output"
    assert result.details["entities"] == {}
    assert result.latency_ms is not None


# ---------------------------------------------------------------------------
# PII fail-path (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_id,expected_entity,text", PII_SAMPLES)
def test_pii_detected_blocks(case_id, expected_entity, text):
    """PII samples are blocked; entity type appears in details; no raw value leaks."""
    validator = PIIValidator(stage="input")
    result = validator.run(text)
    assert result.passed is False, f"Expected block for case {case_id!r}: {text!r}"
    assert result.category == "pii_input"
    assert expected_entity in result.details["entities"], f"Expected {expected_entity!r} in entities for case {case_id!r}"
    # Spans must be pairs of ints
    for spans in result.details["entities"].values():
        for span in spans:
            assert len(span) == 2
            assert isinstance(span[0], int) and isinstance(span[1], int)
    # Security requirement: no raw matched value must appear in details
    _assert_no_raw_pii_in_details(text, result.details)


def _assert_no_raw_pii_in_details(original_text: str, details: dict) -> None:
    """Recursively verify that details contains no substring of original_text that is a PII match."""
    from guardrails._pii_patterns import PII_PATTERNS
    import re

    for pattern_str in PII_PATTERNS.values():
        for match in re.finditer(pattern_str, original_text):
            matched_value = match.group()
            _check_no_value_in_dict(matched_value, details)


def _check_no_value_in_dict(value: str, obj) -> None:
    if isinstance(obj, str):
        assert value not in obj, f"Raw PII value {value!r} found in details string {obj!r}"
    elif isinstance(obj, dict):
        for v in obj.values():
            _check_no_value_in_dict(value, v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _check_no_value_in_dict(value, item)


# ---------------------------------------------------------------------------
# Stage categories (AC2 + AC3)
# ---------------------------------------------------------------------------


def test_input_and_output_categories():
    """Input and output validators produce different categories but same entity detection."""
    text = "Meu CPF é 123.456.789-09"
    in_result = PIIValidator(stage="input").run(text)
    out_result = PIIValidator(stage="output").run(text)
    assert in_result.category == "pii_input"
    assert out_result.category == "pii_output"
    assert in_result.details["entities"] == out_result.details["entities"]


# ---------------------------------------------------------------------------
# Specific AC tests
# ---------------------------------------------------------------------------


def test_cpf_specific_ac1():
    """AC1: CPF in standard format is detected by input validator."""
    result = PIIValidator("input").run("Meu CPF é 123.456.789-09")
    assert result.passed is False
    assert "cpf" in result.details["entities"]


def test_card_specific_ac2():
    """AC2: Card number with dashes is detected by output validator with pii_output category."""
    result = PIIValidator("output").run("4111-1111-1111-1111")
    assert result.passed is False
    assert result.category == "pii_output"


# ---------------------------------------------------------------------------
# Latency budget
# ---------------------------------------------------------------------------


def test_latency_under_target():
    """Regex PII detection on a 1KB input must complete in under 50ms (target <10ms)."""
    text = "Qual é a taxa de juros do empréstimo pessoal? " * 25  # ~1KB
    result = PIIValidator("input").run(text)
    assert result.latency_ms is not None
    assert result.latency_ms < 50, f"Latency {result.latency_ms:.1f}ms exceeded 50ms budget"


# ---------------------------------------------------------------------------
# Presidio NER layer guards
# ---------------------------------------------------------------------------


def _make_presidio_result(entity_type: str, start: int, end: int, score: float):
    """Return a minimal mock of a Presidio RecognizerResult."""
    from unittest.mock import MagicMock

    r = MagicMock()
    r.entity_type = entity_type
    r.start = start
    r.end = end
    r.score = score
    return r


def test_presidio_low_score_is_ignored():
    """Presidio results with score < 0.85 must not trigger a block."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_engine.analyze.return_value = [
        _make_presidio_result("PERSON", 0, 4, 0.50),
    ]
    validator = PIIValidator(stage="input", presidio_engine=mock_engine)
    result = validator.run("João")
    assert result.passed is True
    assert result.details["entities"] == {}


def test_presidio_denylist_term_is_ignored():
    """Presidio results containing a deny-listed token must not trigger a block."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_engine.analyze.return_value = [
        _make_presidio_result("LOCATION", 0, 10, 0.95),  # "Cartão Gold"
    ]
    validator = PIIValidator(stage="input", presidio_engine=mock_engine)
    result = validator.run("Cartão Gold")
    assert result.passed is True
    assert result.details["entities"] == {}


def test_output_stage_skips_presidio_even_when_engine_present():
    """Output validator must NOT call Presidio even if an engine is passed."""
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    validator = PIIValidator(stage="output", presidio_engine=mock_engine)
    result = validator.run("Maria Silva")
    assert result.passed is True
    mock_engine.analyze.assert_not_called()
