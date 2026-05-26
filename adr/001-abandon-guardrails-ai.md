# ADR-001: Abandon guardrails-ai Library

## Status

Accepted (2026-05-25)

## Context

The `guardrails-ai` Python library provides a Hub of pre-built validators, a `Validator` base class, and automatic reask logic. Its advertised LangGraph integration is `guard.to_runnable()`, which produces an LCEL chain. For a native `langgraph.StateGraph` orchestrator, this integration is irrelevant — LCEL chains cannot express conditional pass/block branches that short-circuit before the LLM node.

## Decision

Abandon `guardrails-ai` as a dependency. Define a lightweight `Validator` Protocol and a `ValidatorResult` dataclass in pure Python (`guardrails/validators/base.py`). Each validator is a callable `(text: str) -> ValidatorResult` with no inheritance, no Hub, and no hidden reask logic.

## Consequences

**Positive:**
- Total control over pipeline topology, error handling, and logging.
- Testability without loading Hub artifacts or mocking framework internals.
- No hidden prompt templates or non-deterministic reask loops.

**Negative:**
- Lost built-in reask logic (must implement retry/correction manually if needed).
- Lost access to Hub validators (`DetectPII`, `ToxicLanguage`, etc.) — reimplemented in <50 LOC each.
- Lost community maintenance and versioned releases of validators.

**Neutral:**
- Migration back to `guardrails-ai` remains trivial because the custom `Validator` Protocol mirrors the Hub interface; only the import path changes.
