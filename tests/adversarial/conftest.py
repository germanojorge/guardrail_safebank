"""
Shared fixtures and helpers for adversarial integration tests.

Provides:
- `load_jsonl(path)` — parse JSONL files, skip `#` comment lines
- `full_pipeline_graph` fixture — real validators + mock LLM, session-scoped
- `jsonl_parametrize` helper — yield pytest.param with id from JSONL entries
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from guardrails.adapters.llm import AnthropicProvider
from guardrails.adapters.embedding import SentenceTransformerProvider
from guardrails.adapters.vector_store import InMemoryVectorStore
from guardrails.pipeline.graph import build_graph
from guardrails.validators.toxic import ToxicValidator
from guardrails.validators.pii import PIIValidator
from guardrails.validators.jailbreak import JailbreakValidator
from guardrails.validators.compliance import ComplianceValidator


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file, skipping comment lines starting with ``#``."""
    entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            entries.append(json.loads(stripped))
    return entries


def jsonl_parametrize(fixture_name: str) -> list:
    """Generate ``pytest.param`` entries from a JSONL fixture.

    Each entry yields ``(entry["id"], entry)`` where ``entry`` is the full dict.
    The JSONL is loaded from ``tests/adversarial/fixtures/{fixture_name}``.
    """
    entries = load_jsonl(FIXTURE_DIR / fixture_name)
    return [pytest.param(e["id"], e, id=e["id"]) for e in entries]


@pytest.fixture(scope="session")
def full_pipeline_graph():
    """Build a graph with real validators but a mock LLM provider.

    The mock LLM echoes the input to avoid API cost on every input-side test.
    Validators with heavy model dependencies (Detoxify, DeBERTa) load real models.
    ComplianceValidator gets a mock client (no real API calls) unless overridden.

    Use the ``_with_real_compliance`` fixture below for network-gated tests.
    """
    # Real validators (load real models)
    toxic = ToxicValidator(threshold=0.7)

    pii_input = PIIValidator(stage="input")
    pii_output = PIIValidator(stage="output")

    jailbreak = JailbreakValidator(threshold=0.85)

    # Mock compliance — no API calls
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.input = {
        "verdict": "pass",
        "rule_violated": None,
        "reasoning": "mock",
    }
    mock_response.content = [mock_tool_use]
    mock_response.stop_reason = "tool_use"
    mock_client.messages.create.return_value = mock_response
    compliance = ComplianceValidator(client=mock_client)

    # Mock LLM that echoes input (avoids API cost)
    mock_llm = MagicMock(spec=AnthropicProvider)
    mock_llm.complete.return_value = "Resposta simulada para teste adversarial."

    # Lightweight embedding + in-memory vector store
    emb = SentenceTransformerProvider(
        model_name="intfloat/multilingual-e5-small",
        device="cpu",
    )
    vs = InMemoryVectorStore()
    vs.start_collection(dim=emb.dim)

    return build_graph(
        toxic=toxic,
        pii_input=pii_input,
        pii_output=pii_output,
        jailbreak=jailbreak,
        compliance=compliance,
        llm_provider=mock_llm,
        embedding=emb,
        vector_store=vs,
    )


@pytest.fixture(scope="session")
def full_pipeline_graph_with_real_compliance():
    """Build a graph with real validators AND a real ComplianceValidator.

    Requires ANTHROPIC_API_KEY. Gated behind ``@pytest.mark.network``.
    """
    toxic = ToxicValidator(threshold=0.7)
    pii_input = PIIValidator(stage="input")
    pii_output = PIIValidator(stage="output")
    jailbreak = JailbreakValidator(threshold=0.85)

    compliance = ComplianceValidator(
        model="claude-haiku-4-5-20251001",
        timeout=10.0,
    )

    mock_llm = MagicMock(spec=AnthropicProvider)
    mock_llm.complete.return_value = "Resposta simulada para teste adversarial."

    emb = SentenceTransformerProvider(
        model_name="intfloat/multilingual-e5-small",
        device="cpu",
    )
    vs = InMemoryVectorStore()
    vs.start_collection(dim=emb.dim)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    return build_graph(
        toxic=toxic,
        pii_input=pii_input,
        pii_output=pii_output,
        jailbreak=jailbreak,
        compliance=compliance,
        llm_provider=mock_llm,
        embedding=emb,
        vector_store=vs,
    )


# ---------------------------------------------------------------------------
# Session-finalizer hook for block-rate checking
# ---------------------------------------------------------------------------


class BlockRateTracker:
    """Accumulates block/pass counts and asserts a minimum block rate at session end."""

    def __init__(self, min_rate: float = 0.8):
        self.total = 0
        self.blocked = 0
        self.min_rate = min_rate

    def record(self, blocked: bool) -> None:
        self.total += 1
        if blocked:
            self.blocked += 1

    def finalize(self) -> None:
        if self.total == 0:
            return
        rate = self.blocked / self.total
        print(f"\n[block-rate] {self.blocked}/{self.total} = {rate:.1%} (threshold: {self.min_rate:.0%})")
        if rate < self.min_rate:
            raise AssertionError(f"Block rate {rate:.1%} below threshold {self.min_rate:.0%} ({self.blocked}/{self.total} blocked). See building-rigorously.md §3 — investigate gaps, do NOT lower threshold.")


@pytest.fixture(scope="session")
def block_rate_tracker() -> BlockRateTracker:
    """Session-scoped tracker for block-rate assertions."""
    tracker = BlockRateTracker(min_rate=0.8)

    yield tracker

    tracker.finalize()
