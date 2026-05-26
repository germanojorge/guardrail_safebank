# ADR-002: LangGraph Standalone (No LangChain)

## Status

Accepted (2026-05-25)

## Context

The pipeline requires stateful conditional branching: the input guard must be able to short-circuit to a block node before the LLM generation node ever runs. LCEL chains (`|`) are linear — they cannot express "if input_guard.fail: go to block; else: go to retrieve". LangGraph `StateGraph` with conditional edges (`add_conditional_edges`) models this topology natively.

## Decision

Use `langgraph.StateGraph` with pure-Python node functions and conditional edges. Do not depend on LangChain (`langchain` package). Text splitters and document loaders are reimplemented in <20 LOC where needed; LCEL is not used anywhere.

## Consequences

**Positive:**
- Explicit pass/block topology visible in the graph definition.
- No LangChain versioning surprises or deprecation churn.
- Smaller dependency footprint.

**Negative:**
- Lost LangChain ecosystem utilities (loaders, splitters, memory wrappers).
- Reimplemented splitters may miss edge cases that LangChain handles.

**Neutral:**
- LangChain can be reintroduced later without architectural changes — it would simply become another node function.
