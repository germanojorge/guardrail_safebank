# ADR-003: LLM-as-Judge for Compliance

## Status

Accepted (2026-05-25)

## Context

BACEN and CVM banking compliance rules are semantically subtle. A response like "O CDB do Banco XYZ tem a melhor rentabilidade do mercado" violates R2 (recommending a specific product) but contains no keyword that a regex can reliably match without excessive false positives. A deterministic validator cannot capture the nuance between "explaining options" and "recommending a specific product as ideal".

## Decision

Use Claude Haiku 4.5 as a synchronous LLM judge. Force structured output via an `emit_verdict` tool with schema `{verdict: "PASS" | "BLOCK", rule_violated: "R1"|...|"R5"|null, reasoning: str}`. Evaluate against rubric R1–R5 with 2 few-shot examples per rule. Apply only on output (client questions do not violate compliance).

## Consequences

**Positive:**
- Can detect subtle "Beat 4" violations: an innocent question that produces a plausible but non-compliant answer.
- Tool-use guarantees parseable structured output without regex post-processing.

**Negative:**
- Adds ~5s latency and ~$0.0001 per-request cost.
- Non-deterministic: same input may yield different reasoning on re-runs.
- Closed-loop test bias: rubric, fixtures, and judge authored by the same agent.

**Neutral:**
- Reask 1x with auto-correction is deferred to Extras; MVP uses direct block for predictability.
