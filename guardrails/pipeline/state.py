from __future__ import annotations

from typing import TypedDict


class GraphState(TypedDict):
    message: str
    retrieved_chunks: list[str]
    llm_response: str
    blocked: bool
    block_category: str | None
    block_details: dict | None
    diagnostics: dict


CATEGORY_TOXICITY = "toxicity"
CATEGORY_PII_INPUT = "pii_input"
CATEGORY_PII_OUTPUT = "pii_output"
CATEGORY_JAILBREAK = "jailbreak"
CATEGORY_COMPLIANCE = "compliance"

DIRECTION_INPUT = "input"
DIRECTION_OUTPUT = "output"

SEVERITY_MAP: dict[str, str] = {
    CATEGORY_JAILBREAK: "high",
    CATEGORY_COMPLIANCE: "high",
    CATEGORY_PII_INPUT: "high",
    CATEGORY_PII_OUTPUT: "high",
    CATEGORY_TOXICITY: "medium",
}
