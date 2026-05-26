"""LangGraph StateGraph factory for the guardrail pipeline."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from guardrails.pipeline.nodes import build_nodes
from guardrails.pipeline.state import GraphState


def route_after_input(state: GraphState) -> str:
    return "block_log" if state["blocked"] else "retrieve"


def route_after_output(state: GraphState) -> str:
    return "block_log" if state["blocked"] else END


def build_graph(
    toxic: Any = None,
    pii_input: Any = None,
    pii_output: Any = None,
    jailbreak: Any = None,
    compliance: Any = None,
    llm_provider: Any = None,
    config: dict | None = None,
):
    """Build and compile the guardrail StateGraph.

    All validator/provider args are optional; defaults are created from config
    if not injected. Raises if required deps are missing and no default can be made.
    """
    cfg = config or {}
    v_cfg = cfg.get("validators", {})

    if toxic is None:
        from guardrails.validators.toxic import ToxicValidator

        toxic = ToxicValidator(
            threshold=v_cfg.get("toxicity", {}).get("threshold", 0.7)
        )

    if pii_input is None:
        from guardrails.validators.pii import PIIValidator

        pii_input = PIIValidator(stage="input")

    if pii_output is None:
        from guardrails.validators.pii import PIIValidator

        pii_output = PIIValidator(stage="output")

    if jailbreak is None:
        from guardrails.validators.jailbreak import JailbreakValidator

        jailbreak = JailbreakValidator(
            threshold=v_cfg.get("jailbreak", {}).get("threshold", 0.85)
        )

    if compliance is None:
        from guardrails.validators.compliance import ComplianceValidator

        compliance = ComplianceValidator(
            model=v_cfg.get("compliance", {}).get("model", "claude-haiku-4-5-20251001"),
            timeout=v_cfg.get("compliance", {}).get("timeout", 5.0),
        )

    if llm_provider is None:
        from guardrails.adapters import AnthropicProvider

        llm_provider = AnthropicProvider(
            model=cfg.get("model", "claude-sonnet-4-6-20251105")
        )

    nodes = build_nodes(
        toxic=toxic,
        pii_input=pii_input,
        pii_output=pii_output,
        jailbreak=jailbreak,
        compliance=compliance,
        llm=llm_provider,
    )

    graph = StateGraph(GraphState)

    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.set_entry_point("input_guard")

    graph.add_conditional_edges(
        "input_guard",
        route_after_input,
        {"block_log": "block_log", "retrieve": "retrieve"},
    )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "output_guard")
    graph.add_conditional_edges(
        "output_guard",
        route_after_output,
        {"block_log": "block_log", END: END},
    )
    graph.add_edge("block_log", END)

    return graph.compile()
