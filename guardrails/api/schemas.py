from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LatencyBreakdown(BaseModel):
    input_guard: float | None = None
    retrieve: float | None = None
    rerank: float | None = None
    generate: float | None = None
    output_guard: float | None = None
    total: float


class Diagnostics(BaseModel):
    request_id: str
    validator: str | None = None
    rule_violated: str | None = None
    severity: str | None = None
    latency_ms: LatencyBreakdown
    retrieved_chunks: list[str] | None = None
    block_details: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    blocked: bool
    category: str | None
    diagnostics: Diagnostics


class ModelsLoaded(BaseModel):
    detoxify: bool
    deberta: bool
    anthropic_judge: bool
    anthropic_chat: bool
    embedding: bool
    qdrant_reachable: bool


class HealthResponse(BaseModel):
    status: Literal["ok"]
    validators_loaded: list[str]
    models_loaded: ModelsLoaded


class OutputGuardRequest(BaseModel):
    response: str = Field(min_length=1, max_length=8000)


class OutputGuardResponse(BaseModel):
    blocked: bool
    category: str | None
    rule_violated: str | None
    reasoning: str | None
    latency_ms: float
    details: dict[str, Any] | None
