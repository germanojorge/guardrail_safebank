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
    OutputGuardRequest,
    OutputGuardResponse,
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
    ret_cfg = cfg.get("retrieval", {})

    from guardrails.adapters import (
        AnthropicProvider,
        QdrantStore,
        SentenceTransformerProvider,
    )
    from guardrails.validators.compliance import ComplianceValidator
    from guardrails.validators.jailbreak import JailbreakValidator
    from guardrails.validators.out_of_scope import OutOfScopeValidator
    from guardrails.validators.pii import PIIValidator
    from guardrails.validators.toxic import ToxicValidator

    from guardrails.validators.pii import _build_presidio_engine

    presidio_engine = _build_presidio_engine()

    toxic = ToxicValidator(threshold=v_cfg.get("toxicity", {}).get("threshold", 0.7))
    pii_input = PIIValidator(stage="input", presidio_engine=presidio_engine)
    pii_output = PIIValidator(stage="output", presidio_engine=presidio_engine)
    jailbreak = JailbreakValidator(threshold=v_cfg.get("jailbreak", {}).get("threshold", 0.85))
    out_of_scope = OutOfScopeValidator(
        threshold_in=v_cfg.get("out_of_scope", {}).get("threshold_in", 0.40),
        threshold_out=v_cfg.get("out_of_scope", {}).get("threshold_out", 0.50),
        margin=v_cfg.get("out_of_scope", {}).get("margin", 0.15),
        seeds_path=v_cfg.get("out_of_scope", {}).get("seeds_path", "data/out_of_scope_seeds.json"),
    )
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "mock":
        from guardrails.validators.compliance_rules import RuleBasedComplianceValidator

        compliance = RuleBasedComplianceValidator()
    else:
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
        collection=os.environ.get("QDRANT_COLLECTION") or qd_cfg.get("collection", "itau_faq"),
    )

    reranker = None
    reranker_cfg = ret_cfg.get("reranker", {})
    if reranker_cfg.get("enabled", False):
        from guardrails.adapters import CrossEncoderReranker

        reranker = CrossEncoderReranker(
            model_name=reranker_cfg.get("model", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"),
            device="cpu",
        )

    score_threshold: float | None = ret_cfg.get("score_threshold") or None
    retrieve_top_n: int = ret_cfg.get("top_n", 20)

    graph = build_graph(
        toxic=toxic,
        pii_input=pii_input,
        pii_output=pii_output,
        jailbreak=jailbreak,
        compliance=compliance,
        out_of_scope=out_of_scope,
        llm_provider=llm,
        embedding=embedding,
        vector_store=vector_store,
        reranker=reranker,
        score_threshold=score_threshold,
        retrieve_top_n=retrieve_top_n,
    )
    return graph, toxic, pii_input, jailbreak, compliance, llm, embedding, vector_store, out_of_scope


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    graph, toxic, pii_input, jailbreak, compliance, llm, embedding, vector_store, out_of_scope = _create_components(get_config())
    app.state.graph = graph
    app.state.toxic = toxic
    app.state.pii_input = pii_input
    app.state.jailbreak = jailbreak
    app.state.compliance = compliance
    app.state.out_of_scope = out_of_scope
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
            rerank=diag.get("retrieve_rerank_ms"),
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

    @fast_app.post("/debug/output-guard", response_model=OutputGuardResponse)
    def debug_output_guard(req: OutputGuardRequest, request: Request) -> OutputGuardResponse:
        """Run only the output guard on an arbitrary text.

        Useful for testing whether a given LLM response would be blocked
        without going through the full input → RAG → generate pipeline.
        Always returns HTTP 200; check ``blocked`` to see the verdict.
        """
        import time

        from guardrails.pipeline.state import (
            CATEGORY_COMPLIANCE,
            CATEGORY_PII_OUTPUT,
            CATEGORY_TOXICITY,
        )
        from guardrails.validators.pii import PIIValidator

        toxic = request.app.state.toxic
        pii_output = PIIValidator(stage="output", presidio_engine=request.app.state.pii_input._presidio)
        compliance = request.app.state.compliance

        validators = [
            (toxic, CATEGORY_TOXICITY),
            (pii_output, CATEGORY_PII_OUTPUT),
            (compliance, CATEGORY_COMPLIANCE),
        ]

        t0 = time.perf_counter()
        for validator, category in validators:
            result = validator.run(req.response)
            if not result.passed:
                return OutputGuardResponse(
                    blocked=True,
                    category=category,
                    rule_violated=result.details.get("rule_violated"),
                    reasoning=result.details.get("reasoning"),
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    details=result.details or None,
                )

        return OutputGuardResponse(
            blocked=False,
            category=None,
            rule_violated=None,
            reasoning=None,
            latency_ms=(time.perf_counter() - t0) * 1000,
            details=None,
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
                "out_of_scope",
                "compliance",
            ],
            models_loaded=ModelsLoaded(
                detoxify=request.app.state.toxic._model is not None,
                deberta=request.app.state.jailbreak._pipeline is not None,
                anthropic_judge=getattr(request.app.state.compliance, "client", None) is not None,
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
