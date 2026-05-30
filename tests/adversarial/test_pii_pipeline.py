"""
Adversarial test for the PII guardrail on hand-crafted fixtures.

Uses ``pii_handcrafted.jsonl``. Exercises the ``PIIValidator`` directly (input
stage) rather than the full graph: this isolates PII detection from the other
guardrails (jailbreak/toxicity), so a failure here means a PII gap, not an
incidental hit by another validator.

PII-bearing samples must block; benign samples must pass.

Marked ``@pytest.mark.adversarial`` for CI gating.

NOTE: Known gaps (e.g. 9-digit local phone) are marked ``expected: "allow"``
in the fixture and reflect declared LIMITATIONS.md gaps.
"""

from __future__ import annotations

import pytest

from guardrails.validators.pii import PIIValidator

from .conftest import jsonl_parametrize

pytestmark = pytest.mark.adversarial


@pytest.fixture(scope="module")
def pii_validator() -> PIIValidator:
    """Input-stage PII validator with the real Presidio/spaCy NER layer."""
    return PIIValidator(stage="input")


@pytest.mark.parametrize(
    "sample_id,entry",
    jsonl_parametrize("pii_handcrafted.jsonl"),
)
def test_pii_detection(sample_id: str, entry: dict, pii_validator: PIIValidator):
    """PII-bearing samples block; benign samples pass."""
    text = entry["text"]
    result = pii_validator.run(text)
    expected_block = entry["expected"] == "block"
    is_blocked = not result.passed
    entities = list(result.details["entities"].keys())

    if expected_block:
        assert is_blocked, f"[{sample_id}] expected PII detection but none found: {text!r}"
    else:
        assert not is_blocked, f"[{sample_id}] expected clean but PII detected {entities} (gap: {entry.get('gap', 'none')}): {text!r}"
