"""
Adversarial integration test for the jailbreak guardrail on external fixtures.

Uses ``jailbreak_external.jsonl`` (JailbreakBench EN + PT-BR translations).
Each sample runs through the full guardrail pipeline; the session-finalizer
asserts overall block rate >=80%.

Individual samples do NOT assert — the aggregate block rate is the metric.
This prevents individual DeBERTa gaps from causing cascading failures while
still enforcing the ≥80% acceptance threshold.

Marked ``@pytest.mark.adversarial`` for CI gating.
"""

from __future__ import annotations

import pytest

from .conftest import jsonl_parametrize

pytestmark = pytest.mark.adversarial


@pytest.mark.parametrize(
    "sample_id,entry",
    jsonl_parametrize("jailbreak_external.jsonl"),
)
def test_jailbreak_pipeline_block(
    sample_id: str, entry: dict, full_pipeline_graph, block_rate_tracker
):
    """Track block/pass for aggregate rate check — no individual assertion."""
    result = full_pipeline_graph.invoke(
        {
            "message": entry["text"],
            "diagnostics": {},
        }
    )
    blocked = result.get("blocked", False)
    block_rate_tracker.record(blocked)
