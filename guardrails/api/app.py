from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from structlog.contextvars import bind_contextvars, clear_contextvars

from guardrails.api.schemas import (
    ChatRequest,
    ChatResponse,
    Diagnostics,
    HealthResponse,
    LatencyBreakdown,
    ModelsLoaded,
)
from guardrails.config import get_config
from guardrails.observability.logger import setup_logging
from guardrails.pipeline.graph import build_graph
from guardrails.pipeline.state import SEVERITY_MAP


def _create_components(cfg: dict[str, Any]):
    """Construct all validators, LLM provider, RAG adapters, and compiled graph.

    Separated from the lifespan so tests can patch this single call
    instead of every individual validator constructor.
    """
    v_cfg = cfg.get("validators", {})
    emb_cfg = cfg.get("embedding", {})
    qd_cfg = cfg.get("qdrant", {})

    from guardrails.adapters import (
        AnthropicProvider,
        QdrantStore,
        SentenceTransformerProvider,
    )
    from guardrails.validators.compliance import ComplianceValidator
    from guardrails.validators.jailbreak import JailbreakValidator
    from guardrails.validators.pii import PIIValidator
    from guardrails.validators.toxic import ToxicValidator

    toxic = ToxicValidator(threshold=v_cfg.get("toxicity", {}).get("threshold", 0.7))
    pii_input = PIIValidator(stage="input")
    pii_output = PIIValidator(stage="output")
    jailbreak = JailbreakValidator(threshold=v_cfg.get("jailbreak", {}).get("threshold", 0.85))
    compliance = ComplianceValidator(
        model=v_cfg.get("compliance", {}).get("model", "claude-haiku-4-5-20251001"),
        timeout=v_cfg.get("compliance", {}).get("timeout", 5.0),
    )
    llm = AnthropicProvider(model=cfg.get("model", "claude-sonnet-4-6"))
    embedding = SentenceTransformerProvider(
        model_name=emb_cfg.get("model", "intfloat/multilingual-e5-small"),
        device=emb_cfg.get("device", "cpu"),
        batch_size=emb_cfg.get("batch_size", 32),
    )
    vector_store = QdrantStore(
        host=qd_cfg.get("host", os.environ.get("QDRANT_HOST", "localhost")),
        port=qd_cfg.get("port", 6333),
        collection=qd_cfg.get("collection", "banking_kb"),
    )

    graph = build_graph(
        toxic=toxic,
        pii_input=pii_input,
        pii_output=pii_output,
        jailbreak=jailbreak,
        compliance=compliance,
        llm_provider=llm,
        embedding=embedding,
        vector_store=vector_store,
    )
    return graph, toxic, jailbreak, compliance, llm, embedding, vector_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    graph, toxic, jailbreak, compliance, llm, embedding, vector_store = _create_components(get_config())
    app.state.graph = graph
    app.state.toxic = toxic
    app.state.jailbreak = jailbreak
    app.state.compliance = compliance
    app.state.llm = llm
    app.state.embedding = embedding
    app.state.vector_store = vector_store
    yield


def create_app() -> FastAPI:
    fast_app = FastAPI(lifespan=lifespan, title="LLM Guardrails API")

    @fast_app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            clear_contextvars()
        return response

    @fast_app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, request: Request) -> ChatResponse:
        """Proxy chatbot endpoint with bidirectional guardrails.

        HTTP 200 always — policy blocks are signaled via ``blocked`` field
        in the JSON body (not HTTP status). Check ``response.blocked`` to
        distinguish allowed replies from blocked policy violations.
        """
        result = await request.app.state.graph.ainvoke({"message": req.message, "diagnostics": {}})

        blocked: bool = result["blocked"]
        response_text: str = result["message"] if blocked else result.get("llm_response", "")
        category: str | None = result.get("block_category")
        details: dict = result.get("block_details") or {}

        diag = result.get("diagnostics", {})
        latency = LatencyBreakdown(
            input_guard=diag.get("input_guard_ms"),
            retrieve=diag.get("retrieve_ms"),
            generate=diag.get("generate_ms"),
            output_guard=diag.get("output_guard_ms"),
            total=sum(v for v in diag.values() if isinstance(v, (int, float))),
        )

        severity = SEVERITY_MAP.get(category) if category else None
        rule_violated: str | None = details.get("rule_violated")
        retrieved_chunks = result.get("retrieved_chunks") if not blocked else None
        request_id = getattr(request.state, "request_id", str(uuid4()))

        return ChatResponse(
            response=response_text,
            blocked=blocked,
            category=category,
            diagnostics=Diagnostics(
                request_id=request_id,
                validator=category,
                rule_violated=rule_violated,
                severity=severity,
                latency_ms=latency,
                retrieved_chunks=retrieved_chunks,
                block_details=details if details else None,
            ),
        )

    @fast_app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        return HealthResponse(
            status="ok",
            validators_loaded=[
                "toxic",
                "pii_input",
                "pii_output",
                "jailbreak",
                "compliance",
            ],
            models_loaded=ModelsLoaded(
                detoxify=request.app.state.toxic._model is not None,
                deberta=request.app.state.jailbreak._pipeline is not None,
                anthropic_judge=request.app.state.compliance.client is not None,
                anthropic_chat=request.app.state.llm.client is not None,
                embedding=request.app.state.embedding.model is not None,
                qdrant_reachable=request.app.state.vector_store.is_reachable(),
            ),
        )

    return fast_app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("guardrails.api.app:app", host="0.0.0.0", port=8000, workers=1)
