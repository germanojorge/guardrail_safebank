"""
ComplianceValidator — LLM-as-Judge bancário (BACEN/CVM).

Usa Claude Haiku 4.5 com tool_use forçado (`emit_verdict`) para avaliar outputs
do chatbot contra rubrica R1-R5. Aplicado apenas no output.

`details` keys populated by `run()`:
- `verdict`: "pass" | "fail"
- `rule_violated`: "R1" | "R2" | "R3" | "R4" | "R5" | None
- `reasoning`: str (truncado a 200 chars)
- `model`: str — nome do modelo usado
- `stop_reason`: str | None — stop_reason retornado pela API
- `error`: str | None — nome da exceção se fail-closed (opcional)
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from guardrails.compliance.prompt import build_system_prompt
from guardrails.validators.base import ValidatorResult

VERDICT_TOOL = {
    "name": "emit_verdict",
    "description": "Emitir veredito de compliance bancário para o output do chatbot.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
            "rule_violated": {
                "type": ["string", "null"],
                "enum": [None, "R1", "R2", "R3", "R4", "R5"],
            },
            "reasoning": {"type": "string"},
        },
        "required": ["verdict", "rule_violated", "reasoning"],
    },
}

_REASONING_MAX_CHARS = 200


class ComplianceValidator:
    name = "compliance"

    def __init__(
        self,
        client=None,
        model: str = "claude-haiku-4-5-20251001",
        timeout: float = 5.0,
    ) -> None:
        self.client = client if client is not None else self._create_client(timeout)
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _create_client(timeout: float = 5.0):
        from anthropic import Anthropic

        return Anthropic(timeout=timeout)

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()

        if not text.strip():
            return ValidatorResult(
                passed=True,
                category="compliance",
                score=None,
                details={
                    "verdict": "pass",
                    "rule_violated": None,
                    "reasoning": "",
                    "model": self.model,
                    "stop_reason": None,
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                temperature=0.0,
                system=[
                    {
                        "type": "text",
                        "text": build_system_prompt(),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[VERDICT_TOOL],
                tool_choice={"type": "tool", "name": "emit_verdict"},
                messages=[{"role": "user", "content": text}],
                timeout=self.timeout,
            )

            tool_block = next((b for b in response.content if b.type == "tool_use"), None)
            if tool_block is None:
                return ValidatorResult(
                    passed=False,
                    category="compliance",
                    score=1.0,
                    details={
                        "verdict": "fail",
                        "rule_violated": None,
                        "reasoning": "",
                        "model": self.model,
                        "stop_reason": getattr(response, "stop_reason", None),
                        "error": "judge_no_tool_use",
                    },
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            parsed = tool_block.input
            passed = parsed["verdict"] == "pass"
            score = None if passed else 1.0

            details = {
                "verdict": parsed["verdict"],
                "rule_violated": parsed.get("rule_violated"),
                "reasoning": parsed["reasoning"][:_REASONING_MAX_CHARS],
                "model": self.model,
                "stop_reason": response.stop_reason,
            }
            return ValidatorResult(
                passed=passed,
                category="compliance",
                score=score,
                details=details,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        except Exception as e:
            return ValidatorResult(
                passed=False,
                category="compliance",
                score=1.0,
                details={
                    "verdict": "fail",
                    "rule_violated": None,
                    "reasoning": "",
                    "model": self.model,
                    "stop_reason": None,
                    "error": type(e).__name__,
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
