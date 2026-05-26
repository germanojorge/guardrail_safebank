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

RETRIEVE_TOP_K = 3


def build_nodes(
    toxic: Any,
    pii_input: Any,
    pii_output: Any,
    jailbreak: Any,
    compliance: Any,
    llm: Any,
    embedding: Any = None,
    vector_store: Any = None,
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
        chunks: list[str] = []
        embed_ms: float = 0.0
        search_ms: float = 0.0

        if embedding is not None and vector_store is not None:
            t_embed = time.perf_counter()
            try:
                query_vec = embedding.embed_queries([state["message"]])[0]
            except Exception:
                query_vec = None
            embed_ms = (time.perf_counter() - t_embed) * 1000

            if query_vec is not None:
                t_search = time.perf_counter()
                hits = vector_store.search(query_vec, top_k=RETRIEVE_TOP_K)
                search_ms = (time.perf_counter() - t_search) * 1000
                chunks = [h.text for h in hits if h.text]

        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "retrieved_chunks": chunks,
            "diagnostics": {
                **state.get("diagnostics", {}),
                "retrieve_ms": elapsed,
                "retrieve_embed_ms": embed_ms,
                "retrieve_search_ms": search_ms,
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
