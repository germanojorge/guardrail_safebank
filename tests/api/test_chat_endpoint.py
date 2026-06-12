"""Tests for POST /chat endpoint — covers all 5 AC items."""

from __future__ import annotations

import concurrent.futures
import uuid

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# AC1: Benign request returns response + diagnostics + retrieved_chunks
# ---------------------------------------------------------------------------


def test_chat_benign_returns_response_and_diagnostics(client: TestClient):
    resp = client.post("/chat", json={"message": "Como funciona o cartão Gold?"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["blocked"] is False
    assert body["category"] is None
    assert body["response"] == "Olá! Como posso ajudar?"

    diag = body["diagnostics"]
    assert diag["retrieved_chunks"] is not None
    assert len(diag["retrieved_chunks"]) > 0
    first_chunk = diag["retrieved_chunks"][0]
    assert "text" in first_chunk

    lat = diag["latency_ms"]
    assert lat["input_guard"] is not None
    assert lat["retrieve"] is not None
    assert lat["generate"] is not None
    assert lat["output_guard"] is not None
    assert lat["total"] > 0


# ---------------------------------------------------------------------------
# AC2: PII input block
# ---------------------------------------------------------------------------


def test_chat_pii_input_blocked(make_client):
    app = make_client(
        pii_input_passes=False,
        pii_input_details={"entities": {"cpf": [(0, 14)]}},
    )
    with TestClient(app) as tc:
        resp = tc.post("/chat", json={"message": "Meu CPF é 123.456.789-09"})

    assert resp.status_code == 200
    body = resp.json()

    assert body["blocked"] is True
    assert body["category"] == "pii_input"

    diag = body["diagnostics"]
    assert diag["validator"] == "pii_input"
    assert diag["block_details"] is not None
    assert "entities" in diag["block_details"]
    assert diag["retrieved_chunks"] is None


# ---------------------------------------------------------------------------
# AC3: Compliance R2 output block (Beat 4)
# ---------------------------------------------------------------------------


def test_chat_compliance_r2_blocked(make_client):
    app = make_client(
        compliance_passes=False,
        compliance_details={
            "verdict": "fail",
            "rule_violated": "R2",
            "reasoning": "Recomendação específica de investimento.",
        },
        llm_response="Recomendo investir 100% em ações da Petrobras.",
    )
    with TestClient(app) as tc:
        resp = tc.post("/chat", json={"message": "Como devo investir meu dinheiro?"})

    assert resp.status_code == 200
    body = resp.json()

    assert body["blocked"] is True
    assert body["category"] == "compliance"

    diag = body["diagnostics"]
    assert diag["rule_violated"] == "R2"
    assert diag["severity"] == "high"


# ---------------------------------------------------------------------------
# AC4 (partial): request_id echoed in diagnostics
# ---------------------------------------------------------------------------


def test_chat_returns_request_id(client: TestClient):
    resp = client.post("/chat", json={"message": "Olá"})
    assert resp.status_code == 200
    request_id = resp.json()["diagnostics"]["request_id"]
    uuid.UUID(request_id)  # raises ValueError if not valid UUID


def test_chat_echoes_provided_request_id(client: TestClient):
    custom_id = str(uuid.uuid4())
    resp = client.post(
        "/chat",
        json={"message": "Olá"},
        headers={"x-request-id": custom_id},
    )
    assert resp.status_code == 200
    assert resp.json()["diagnostics"]["request_id"] == custom_id


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_chat_validates_empty_message(client: TestClient):
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_validates_missing_message(client: TestClient):
    resp = client.post("/chat", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC5: 5 concurrent requests — no 500s
# ---------------------------------------------------------------------------


def test_chat_handles_5_concurrent_requests(client: TestClient):
    def fire(_):
        return client.post("/chat", json={"message": "Olá, tudo bem?"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fire, range(5)))

    for r in results:
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
