"""Pipeline node factories for the LangGraph guardrail pipeline."""

from __future__ import annotations

import time
from typing import Any, Callable

from guardrails.observability import log_blocked_event, log_passed_event
from guardrails.pipeline.state import (
    CATEGORY_COMPLIANCE,
    CATEGORY_JAILBREAK,
    CATEGORY_PII_INPUT,
    CATEGORY_PII_OUTPUT,
    CATEGORY_TOXICITY,
    DIRECTION_INPUT,
    DIRECTION_OUTPUT,
    SEVERITY_MAP,
    GraphState,
)

CHATBOT_SYSTEM_PROMPT = """Você é um atendente bancário prestativo do Banco Seguro.
Responda dúvidas sobre produtos bancários com base nos documentos fornecidos.
Seja educado, claro e objetivo. Use português brasileiro.
Se não souber a resposta, diga que não tem essa informação e sugira falar com um gerente."""

FALLBACK_RESPONSE = "Sua mensagem não pôde ser processada porque viola nossas políticas de segurança. Por favor, reformule sua pergunta."

_MOCK_CHUNKS = [
    "Cartão Gold do Banco Seguro: limite de R$ 5.000, cashback 1,5%, sem anuidade no primeiro ano.",
    "Investimentos: CDB com rendimento de 110% do CDI, liquidez diária disponível.",
    "Atendimento disponível 24h pelo canal digital. Agências abertas de seg-sex das 9h às 16h.",
]


def build_nodes(
    toxic: Any,
    pii_input: Any,
    pii_output: Any,
    jailbreak: Any,
    compliance: Any,
    llm: Any,
) -> dict[str, Callable[[GraphState], dict]]:
    """Return a dict of node functions with injected validator/provider instances."""

    def input_guard(state: GraphState) -> dict:
        t0 = time.perf_counter()
        text = state["message"]
        validators = [
            (toxic, CATEGORY_TOXICITY),
            (pii_input, CATEGORY_PII_INPUT),
            (jailbreak, CATEGORY_JAILBREAK),
        ]
        for validator, category in validators:
            result = validator.run(text)
            if not result.passed:
                log_blocked_event(
                    direction=DIRECTION_INPUT,
                    category=category,
                    severity=SEVERITY_MAP[category],
                    rule_violated=result.details.get("rule_violated"),
                    latency_ms=result.latency_ms,
                    input_text=text,
                    extra=result.details,
                )
                return {
                    "blocked": True,
                    "block_category": category,
                    "block_details": result.details,
                    "diagnostics": {
                        **state.get("diagnostics", {}),
                        "input_guard_ms": (time.perf_counter() - t0) * 1000,
                    },
                }
        log_passed_event(
            direction=DIRECTION_INPUT,
            category="all",
            latency_ms=(time.perf_counter() - t0) * 1000,
            input_text=text,
        )
        return {
            "blocked": False,
            "block_category": None,
            "block_details": None,
            "diagnostics": {
                **state.get("diagnostics", {}),
                "input_guard_ms": (time.perf_counter() - t0) * 1000,
            },
        }

    def retrieve(state: GraphState) -> dict:
        t0 = time.perf_counter()
        chunks = list(_MOCK_CHUNKS)
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "retrieved_chunks": chunks,
            "diagnostics": {
                **state.get("diagnostics", {}),
                "retrieve_ms": elapsed,
            },
        }

    def generate(state: GraphState) -> dict:
        t0 = time.perf_counter()
        chunks = state.get("retrieved_chunks", [])
        context_block = "\n".join(f"- {c}" for c in chunks)
        messages = [
            {
                "role": "user",
                "content": f"Documentos:\n{context_block}\n\nPergunta: {state['message']}",
            },
        ]
        system_msg = CHATBOT_SYSTEM_PROMPT
        response = llm.complete(
            messages=messages,
            model=None,
        )
        _ = system_msg  # system prompt used via provider default setup
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "llm_response": response,
            "diagnostics": {
                **state.get("diagnostics", {}),
                "generate_ms": elapsed,
            },
        }

    def output_guard(state: GraphState) -> dict:
        t0 = time.perf_counter()
        text = state["llm_response"]
        validators = [
            (toxic, CATEGORY_TOXICITY),
            (pii_output, CATEGORY_PII_OUTPUT),
            (compliance, CATEGORY_COMPLIANCE),
        ]
        for validator, category in validators:
            result = validator.run(text)
            if not result.passed:
                log_blocked_event(
                    direction=DIRECTION_OUTPUT,
                    category=category,
                    severity=SEVERITY_MAP[category],
                    rule_violated=result.details.get("rule_violated"),
                    latency_ms=result.latency_ms,
                    input_text=text,
                    extra=result.details,
                )
                return {
                    "blocked": True,
                    "block_category": category,
                    "block_details": result.details,
                    "diagnostics": {
                        **state.get("diagnostics", {}),
                        "output_guard_ms": (time.perf_counter() - t0) * 1000,
                    },
                }
        log_passed_event(
            direction=DIRECTION_OUTPUT,
            category="all",
            latency_ms=(time.perf_counter() - t0) * 1000,
            input_text=text,
        )
        return {
            "blocked": False,
            "block_category": None,
            "block_details": None,
            "diagnostics": {
                **state.get("diagnostics", {}),
                "output_guard_ms": (time.perf_counter() - t0) * 1000,
            },
        }

    def block_log(state: GraphState) -> dict:
        return {"message": FALLBACK_RESPONSE}

    return {
        "input_guard": input_guard,
        "retrieve": retrieve,
        "generate": generate,
        "output_guard": output_guard,
        "block_log": block_log,
    }
