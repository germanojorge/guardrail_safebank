"""
Adversarial integration test for the Compliance guardrail on hand-crafted fixtures.

Uses ``compliance_handcrafted.jsonl``. Requires ANTHROPIC_API_KEY.

Marked ``@pytest.mark.network`` (skipped in offline CI).
"""

from __future__ import annotations

import os

import pytest

from .conftest import jsonl_parametrize

pytestmark = [
    pytest.mark.adversarial,
    pytest.mark.network,
]


@pytest.fixture(scope="module")
def needs_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — skipping compliance tests")


@pytest.mark.parametrize(
    "sample_id,entry",
    jsonl_parametrize("compliance_handcrafted.jsonl"),
)
def test_compliance_pipeline_verdict(
    sample_id: str,
    entry: dict,
    full_pipeline_graph_with_real_compliance,
    needs_api_key,
):
    """Compliance fixtures must match expected verdict and rule."""
    graph = full_pipeline_graph_with_real_compliance
    result = graph.invoke(
        {
            "message": entry["text"],
            "diagnostics": {},
        }
    )
    expected = entry["expected"]
    is_blocked = result.get("blocked", False)

    if expected == "block":
        assert is_blocked, f"[{sample_id}] Expected block for: {entry['text']!r}\n  details: {result.get('block_details', {})}"
        expected_rule = entry.get("expected_rule_violated")
        if expected_rule:
            block_details = result.get("block_details", {})
            actual_rule = block_details.get("rule_violated")
            assert actual_rule == expected_rule, f"[{sample_id}] Expected rule {expected_rule}, got {actual_rule}\n  details: {block_details}"
    else:
        if is_blocked:
            print(f"[{sample_id}] Allowed text blocked (possible false positive): {entry['text']!r}")
        assert not is_blocked, f"[{sample_id}] Expected pass for benign sample: {entry['text']!r}"
