"""
Unit tests for structured JSON logger (guardrails/observability/logger.py).

Tests use structlog.testing.capture_logs to capture log events without stdout.
"""

import hashlib
import re

from structlog.testing import capture_logs

from guardrails.observability.logger import (
    _compute_input_hash,
    log_blocked_event,
    log_passed_event,
    sanitize_for_log,
)


# ---------------------------------------------------------------------------
# _compute_input_hash
# ---------------------------------------------------------------------------


def test_input_hash_is_sha256_hex():
    h = _compute_input_hash("Olá, mundo!")
    assert isinstance(h, str)
    assert len(h) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_input_hash_deterministic():
    text = "Qual é o saldo da minha conta?"
    assert _compute_input_hash(text) == _compute_input_hash(text)


def test_input_hash_truncated_to_200_chars():
    text = "x" * 500
    h = _compute_input_hash(text)
    expected_input = text[:200]
    assert h == hashlib.sha256(expected_input.encode()).hexdigest()


# ---------------------------------------------------------------------------
# sanitize_for_log
# ---------------------------------------------------------------------------


def test_sanitize_redacts_email():
    result = sanitize_for_log("Meu email é joao@example.com")
    assert "joao@example.com" not in result
    assert "[REDACTED_email]" in result


def test_sanitize_redacts_cpf():
    result = sanitize_for_log("CPF: 123.456.789-09")
    assert "123.456.789-09" not in result
    assert "[REDACTED_cpf]" in result


def test_sanitize_redacts_card():
    result = sanitize_for_log("Cartão: 4111-1111-1111-1111")
    assert "4111-1111-1111-1111" not in result
    assert "[REDACTED_cartao]" in result


def test_sanitize_redacts_phone():
    result = sanitize_for_log("Tel: 011-912-3456")
    assert "011-912-3456" not in result
    assert "[REDACTED_telefone]" in result


def test_sanitize_benign_text_unchanged():
    text = "Qual é a taxa de juros do empréstimo pessoal?"
    assert sanitize_for_log(text) == text


# ---------------------------------------------------------------------------
# log_blocked_event — schema completeness
# ---------------------------------------------------------------------------


def test_blocked_event_has_required_fields():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="pii",
            severity="high",
        )
    assert len(cap_logs) == 1
    event = cap_logs[0]
    assert event["event"] == "validator.blocked"
    assert event["log_level"] == "info"
    assert event["direction"] == "input"
    assert event["category"] == "pii"
    assert event["severity"] == "high"


def test_blocked_event_includes_input_hash_when_provided():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="jailbreak",
            severity="high",
            input_text="Test input",
        )
    event = cap_logs[0]
    assert event["input_hash"] is not None
    assert isinstance(event["input_hash"], str)
    assert len(event["input_hash"]) == 64


def test_blocked_event_includes_latency():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="output",
            category="compliance",
            severity="high",
            latency_ms=42.5,
        )
    event = cap_logs[0]
    assert event["latency_ms"] == 42.5


def test_blocked_event_includes_snippet_when_text_provided():
    """blocked event includes PII-sanitized snippet when input_text is given."""
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="pii",
            severity="high",
            input_text="Meu email é joao@example.com e CPF 123.456.789-09",
        )
    event = cap_logs[0]
    assert "snippet" in event
    assert "[REDACTED_email]" in event["snippet"]
    assert "[REDACTED_cpf]" in event["snippet"]
    assert "joao@example.com" not in event["snippet"]


def test_blocked_event_omits_snippet_when_no_text():
    """blocked event has no snippet field when input_text is None."""
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="toxicity",
            severity="high",
        )
    event = cap_logs[0]
    assert "snippet" not in event


def test_passed_event_includes_snippet_when_text_provided():
    """passed event includes PII-sanitized snippet when input_text is given."""
    with capture_logs() as cap_logs:
        log_passed_event(
            direction="input",
            category="toxicity",
            input_text="Meu CPF é 123.456.789-09",
        )
    event = cap_logs[0]
    assert "snippet" in event
    assert "[REDACTED_cpf]" in event["snippet"]


def test_blocked_event_includes_rule_violated():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="output",
            category="compliance",
            severity="high",
            rule_violated="R2",
        )
    event = cap_logs[0]
    assert event["rule_violated"] == "R2"


def test_blocked_event_omits_rule_violated_when_none():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="toxicity",
            severity="high",
        )
    event = cap_logs[0]
    assert "rule_violated" not in event


# ---------------------------------------------------------------------------
# log_blocked_event — extra fields pass-through
# ---------------------------------------------------------------------------


def test_blocked_event_passes_extra_fields():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="jailbreak",
            severity="high",
            extra={"layer_caught": "substring", "substring_match_count": 3},
        )
    event = cap_logs[0]
    assert event["layer_caught"] == "substring"
    assert event["substring_match_count"] == 3


# ---------------------------------------------------------------------------
# log_passed_event
# ---------------------------------------------------------------------------


def test_passed_event_has_event_name_and_fields():
    with capture_logs() as cap_logs:
        log_passed_event(
            direction="input",
            category="toxicity",
        )
    assert len(cap_logs) == 1
    event = cap_logs[0]
    assert event["event"] == "validator.passed"
    assert event["direction"] == "input"
    assert event["category"] == "toxicity"


def test_passed_event_includes_input_hash():
    with capture_logs() as cap_logs:
        log_passed_event(
            direction="input",
            category="pii",
            input_text="Olá",
        )
    event = cap_logs[0]
    assert event["input_hash"] is not None


def test_passed_event_passes_extra_fields():
    with capture_logs() as cap_logs:
        log_passed_event(
            direction="output",
            category="compliance",
            extra={"rule_violated": None},
        )
    event = cap_logs[0]
    assert event["rule_violated"] is None


# ---------------------------------------------------------------------------
# Security: PII value never appears in logged fields
# ---------------------------------------------------------------------------


def test_input_hash_never_raw_pii():
    text = "Meu CPF é 123.456.789-09 e cartão 4111-1111-1111-1111"
    h = _compute_input_hash(text)
    assert "123.456.789-09" not in h
    assert "4111-1111-1111-1111" not in h


def test_blocked_event_hash_not_raw_pii():
    text_with_pii = "Meu email é maria@banco.com.br"
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="pii",
            severity="high",
            input_text=text_with_pii,
        )
    event = cap_logs[0]
    assert "maria@banco.com.br" not in str(event["input_hash"])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_text_does_not_crash():
    with capture_logs():
        log_blocked_event(
            direction="input",
            category="toxicity",
            severity="medium",
            input_text="",
        )
        log_passed_event(
            direction="output",
            category="pii",
            input_text="",
        )


def test_none_input_text_produces_none_hash():
    with capture_logs() as cap_logs:
        log_blocked_event(
            direction="input",
            category="toxicity",
            severity="medium",
            input_text=None,
        )
    event = cap_logs[0]
    assert event["input_hash"] is None
