"""
Structured JSON logger for the guardrails pipeline.

Log schema for `log_blocked_event`:
- `timestamp`: ISO 8601 datetime string
- `event`: "validator.blocked"
- `direction`: "input" | "output"
- `category`: validator category
- `severity`: "high" | "medium" | "low"
- `rule_violated`: "R1"-"R5" | None
- `input_hash`: SHA-256 hex digest of first 200 chars
- `latency_ms`: float | None

Extra keys (via `extra` dict): `layer_caught`, `substring_match_count`, etc.
Log events also include a `snippet` field with the first 100 chars of PII-sanitized
input for debugging, when `input_text` is provided.
"""

from __future__ import annotations

import hashlib
from typing import Any

from guardrails._pii_patterns import COMPILED_PII

INPUT_HASH_MAX_CHARS = 200
SNIPPET_MAX_CHARS = 100
LOGGER_NAME = "guardrails"


def _compute_input_hash(text: str) -> str:
    return hashlib.sha256(text[:INPUT_HASH_MAX_CHARS].encode()).hexdigest()


def sanitize_for_log(text: str) -> str:
    result = text
    for entity_type, pattern in COMPILED_PII.items():
        result = pattern.sub(f"[REDACTED_{entity_type}]", result)
    return result


def setup_logging() -> None:
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def log_blocked_event(
    *,
    direction: str,
    category: str,
    severity: str,
    rule_violated: str | None = None,
    latency_ms: float | None = None,
    input_text: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    import structlog

    fields: dict[str, Any] = {
        "direction": direction,
        "category": category,
        "severity": severity,
        "input_hash": _compute_input_hash(input_text) if input_text else None,
        "latency_ms": latency_ms,
    }
    if input_text is not None:
        sanitized = sanitize_for_log(input_text)
        fields["snippet"] = sanitized[:SNIPPET_MAX_CHARS]
    if rule_violated is not None:
        fields["rule_violated"] = rule_violated
    if extra:
        fields.update(extra)

    structlog.get_logger(LOGGER_NAME).info("validator.blocked", **fields)


def log_passed_event(
    *,
    direction: str,
    category: str,
    latency_ms: float | None = None,
    input_text: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    import structlog

    fields: dict[str, Any] = {
        "direction": direction,
        "category": category,
        "input_hash": _compute_input_hash(input_text) if input_text else None,
        "latency_ms": latency_ms,
    }
    if input_text is not None:
        sanitized = sanitize_for_log(input_text)
        fields["snippet"] = sanitized[:SNIPPET_MAX_CHARS]
    if extra:
        fields.update(extra)

    structlog.get_logger(LOGGER_NAME).info("validator.passed", **fields)
