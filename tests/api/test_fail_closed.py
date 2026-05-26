"""Adversarial gate: verify compliance fail-closed surfaces as HTTP block.

Building-rigorously §2: ComplianceValidator.run() catches all exceptions and
returns ValidatorResult(passed=False, ..., error=ExceptionType). This test
verifies that response propagates correctly through the HTTP layer as a 200
with blocked=True — not as a 500.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_compliance_fail_closed_blocks_via_http(make_client):
    """Compliance fail-closed result (passed=False with error key) → HTTP 200, blocked=True."""
    app = make_client(
        compliance_passes=False,
        compliance_details={
            "verdict": "fail",
            "rule_violated": None,
            "reasoning": "",
            "model": "claude-haiku-4-5-20251001",
            "stop_reason": None,
            "error": "APITimeoutError",
        },
        llm_response="Claro, posso ajudar com isso.",
    )
    with TestClient(app) as tc:
        resp = tc.post("/chat", json={"message": "Como devo investir?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is True
    assert body["category"] == "compliance"
    assert body["diagnostics"]["block_details"]["error"] == "APITimeoutError"
