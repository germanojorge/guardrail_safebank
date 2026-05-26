# ADR-004: Layered Jailbreak Defense

## Status

Accepted (2026-05-25)

## Context

JailbreakBench shows that naive substring filters fail against >80% of paraphrased attacks. A single-layer defense is insufficient for a banking guardrail where a single bypass can expose the system to prompt injection. Per `building-rigorously.md §6`: "substring matching is almost never a guardrail".

## Decision

Implement a two-layer defense:
- **Layer 1 (fast-path):** Substring matching against ~20 known jailbreak keywords in PT-BR and English. Latency <5ms.
- **Layer 2 (deep):** `protectai/deberta-v3-base-prompt-injection-v2` via Hugging Face Transformers. Latency <300ms on CPU. Only runs if Layer 1 passes.

Either layer blocking produces `passed=False` with `details["layer_caught"]` set to `"substring"` or `"deberta"`.

## Consequences

**Positive:**
- High recall: 100% block rate on JailbreakBench PT-BR + EN fixtures (22/22).
- Layer 1 absorbs cheap attacks without loading the model.

**Negative:**
- ~1GB model memory footprint.
- ~300ms CPU latency when Layer 2 runs.
- Ongoing keyword list maintenance toil for Layer 1.
- DeBERTa is English-trained; PT-BR paraphrasing with no English keywords may have lower recall than measured.
