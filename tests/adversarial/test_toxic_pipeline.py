"""
Adversarial integration test for the toxicity guardrail on external fixtures.

Uses ``toxic_external.jsonl`` (HateBR PT-BR + RealToxicityPrompts EN).
Each sample runs through the full guardrail pipeline; the session-finalizer
asserts overall block rate >=80%.

Marked ``@pytest.mark.adversarial`` for CI gating.
"""

from __future__ import annotations

import pytest

from .conftest import jsonl_parametrize

pytestmark = pytest.mark.adversarial


@pytest.mark.parametrize(
    "sample_id,entry",
    jsonl_parametrize("toxic_external.jsonl"),
)
def test_toxic_pipeline_block(sample_id: str, entry: dict, full_pipeline_graph, block_rate_tracker):
    """Track block/pass for aggregate rate check — no individual assertion."""
    result = full_pipeline_graph.invoke(
        {
            "message": entry["text"],
            "diagnostics": {},
        }
    )
    blocked = result.get("blocked", False)
    block_rate_tracker.record(blocked)
