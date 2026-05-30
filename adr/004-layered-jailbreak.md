# ADR-004: Layered Jailbreak Defense

## Status

Accepted (2026-05-25), amended (2026-05-27), amended (2026-05-28)

## Context

JailbreakBench shows that naive substring filters fail against >80% of paraphrased attacks. A single-layer defense is insufficient for a banking guardrail where a single bypass can expose the system to prompt injection. Per `building-rigorously.md §6`: "substring matching is almost never a guardrail".

## Decision

Implement a two-layer defense:
- **Layer 1 (fast-path):** Deterministic regex rules with named, explainable patterns. Each rule targets a specific attack pattern (instruction override, role change, instruction extraction, policy conflict, suspicious chaining, DAN mode, isolated keywords) using context windows (`.{0,N}`) and character class alternation (`[çc]`, `[oõ]`) to catch paraphrased variants. Named rules provide auditability — the bank can explain exactly which pattern fired. Latency <1ms.
- **Layer 2 (deep):** `meta-llama/Llama-Prompt-Guard-2-86M` via Hugging Face Transformers. Latency <300ms on CPU. Only runs if Layer 1 passes.

Either layer blocking produces `passed=False` with `details["layer_caught"]` set to `"regex"` or `"deberta"`.

> **Amendment 2026-05-27:** Layer 2 was originally `protectai/deberta-v3-base-prompt-injection-v2`. That model is English-centric and flagged benign PT-BR banking phrases as INJECTION at ~1.0 confidence (false positives that would block normal customer traffic). Switched to Meta Prompt-Guard-2 (mDeBERTa-based, multilingual — officially evaluated in 8 languages incl. Portuguese). Note: it is a **gated** HF repo, so builds/runtime require an accepted license + HF token. Label scheme changed from `SAFE`/`INJECTION` to `LABEL_0`/`LABEL_1`; the validator handles both.

> **Amendment 2026-05-28:** Layer 1 was upgraded from simple substring keyword matching to deterministic regex rules with named patterns. This improves explainability (compliance can see exactly which rule fired, e.g. `sobrescrita_instrucoes` vs `mudanca_papel`) and coverage (context windows catch paraphrased variants without exact substring matching). The `layer_caught` value changed from `"substring"` to `"regex"`. Detail keys changed from `substring_match_count`/`substring_keywords_checked` to `matched_rules`/`rules_checked`.

## Consequences

**Positive:**
- High recall: 100% block rate on JailbreakBench PT-BR + EN fixtures (22/22).
- Layer 1 absorbs cheap attacks without loading the model.
- Named rules provide compliance-grade explainability for each block.
- Context windows catch paraphrased variants (e.g. "ignore completamente todas as suas instruções") that exact substring matching would miss.

**Negative:**
- ~1GB model memory footprint.
- ~300ms CPU latency when Layer 2 runs.
- Regex rules require maintenance as new attack patterns emerge.
- DeBERTa is English-trained; PT-BR paraphrasing with no English keywords may have lower recall than measured.