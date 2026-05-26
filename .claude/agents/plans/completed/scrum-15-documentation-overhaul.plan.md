# Plan: SCRUM-15 Documentation Overhaul

## Summary

Overhaul the project documentation to establish technical credibility via radical honesty. This involves rewriting README.md with an 8-minute live demo storyboard, creating 6 Architecture Decision Records (ADRs) in the Michael Nygard format documenting critical pivots from the 2026-05-25 grilling session, and applying final refinements to LIMITATIONS.md (already exceeds ≥8 gap requirement with 23 confirmed gaps). The deliverable must enable a first-time cloner to run `docker compose up` in <5 minutes and understand every major architectural trade-off.

## User Story

As an evaluator of this technical interview project
I want a clear README with an 8-minute demo script, LIMITATIONS.md with ≥8 confirmed gaps, and concise ADRs for critical architectural decisions
So that credibility is built via technical honesty rather than marketing discourse

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | Documentation only (no runtime code) |
| Jira Issue | SCRUM-15 |

---

## Patterns to Follow

### Naming
```
// SOURCE: guardrails/validators/base.py:18-24
@dataclass
class ValidatorResult:
    passed: bool
    category: str
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None
```
Pattern: Use Python 3.12+ syntax (`| None`, `@dataclass`, `field(default_factory=...)`). Keep ADR filenames kebab-case with numeric prefix.

### Error Handling
```
// SOURCE: guardrails/validators/compliance.py (fail-closed design)
# All validators catch exceptions and return blocking results.
# This "fail-closed" principle is reflected in docs by documenting
# every gap as a CONFIRMED limitation, not a hypothetical edge case.
```
Pattern: Documentation follows the same fail-closed philosophy as the code — every known weakness is declared upfront.

### Tests
```
// SOURCE: pyproject.toml:40-49
markers = [
    "slow: marks tests that load heavy ML models (deselect with -m 'not slow')",
    "adversarial: marks adversarial integration tests (external fixtures, full pipeline)",
    "network: marks tests that require external API calls (Anthropic, HF datasets download)",
]
```
Pattern: Document pytest markers so evaluators know which tests require what resources.

### ADR Format
```
// SOURCE: industry standard (Michael Nygard)
# ADR-XXX: Title

## Status
Accepted (YYYY-MM-DD)

## Context
The forces at play...

## Decision
What we decided...

## Consequences
Positive, negative, and neutral...
```
Pattern: <300 words per ADR. No "alternatives considered" section unless it illuminates the trade-off.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE (overwrite) | Overhaul with demo storyboard, CI mention, test commands, observability narrative, memory warning |
| `LIMITATIONS.md` | UPDATE (patch) | Add toxicity section, infra/scaling section, accepted risks subsection, date-stamp metrics table |
| `adr/001-abandon-guardrails-ai.md` | CREATE | Document pivot from guardrails-ai library to custom validators |
| `adr/002-langgraph-standalone.md` | CREATE | Document LangGraph without LangChain decision |
| `adr/003-llm-judge-compliance.md` | CREATE | Document Claude Haiku + tool_use for compliance judge |
| `adr/004-layered-jailbreak.md` | CREATE | Document substring + DeBERTa layered defense |
| `adr/005-regex-pii-no-presidio.md` | CREATE | Document regex-only PII over Presidio Analyzer |
| `adr/006-local-embeddings.md` | CREATE | Document sentence-transformers E5 over Voyage AI |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create ADR directory and ADR 001

- **File**: `adr/001-abandon-guardrails-ai.md`
- **Action**: CREATE
- **Implement**: Write ADR documenting the abandonment of the `guardrails-ai` Python library in favor of custom Protocol-based validators. Context: library's LangGraph integration was only `guard.to_runnable()` (LCEL), irrelevant for a LangGraph-native orchestrator. Decision: define `Validator` Protocol + `ValidatorResult` dataclass. Consequences: gained total pipeline control and testability; lost built-in reask, Hub validators, and community maintenance.
- **Mirror**: Follow Michael Nygard format. Keep under 300 words.
- **Validate**: Word count < 300. Readability check.

### Task 2: Create ADR 002

- **File**: `adr/002-langgraph-standalone.md`
- **Action**: CREATE
- **Implement**: Document decision to use LangGraph `StateGraph` without LangChain. Context: pipeline needs stateful conditional branching (input guard can short-circuit to block before LLM). LCEL chains cannot express this cleanly. Decision: pure-Python nodes in StateGraph with conditional edges. Consequences: explicit pass/block topology; lost LangChain ecosystem utilities (text splitters, loaders).
- **Mirror**: Same format as ADR 001.
- **Validate**: Word count < 300.

### Task 3: Create ADR 003

- **File**: `adr/003-llm-judge-compliance.md`
- **Action**: CREATE
- **Implement**: Document the only non-deterministic validator. Context: BACEN/CVM compliance rules (promessa de rendimento, recomendação específica) are too semantically subtle for regex. Decision: Claude Haiku 4.5 with forced `emit_verdict` tool_use for structured output against rubric R1-R5. Consequences: can detect subtle "Beat 4" violations; adds ~5s latency, per-request cost, non-determinism, closed-loop test bias.
- **Mirror**: Same format.
- **Validate**: Word count < 300. Explicitly mention "Beat 4" as the killer demo feature.

### Task 4: Create ADR 004

- **File**: `adr/004-layered-jailbreak.md`
- **Action**: CREATE
- **Implement**: Document two-layer defense. Context: JailbreakBench shows >80% paraphrased attacks bypass naive substring filters. Decision: Layer 1 (substring fast-path, <5ms) + Layer 2 (DeBERTa HF `protectai/deberta-v3-base-prompt-injection-v2`, <300ms CPU). Consequences: high recall; ~1GB model memory, ~300ms CPU latency when Layer 2 runs, keyword list maintenance toil.
- **Mirror**: Same format. Reference `building-rigorously.md §6`.
- **Validate**: Word count < 300.

### Task 5: Create ADR 005

- **File**: `adr/005-regex-pii-no-presidio.md`
- **Action**: CREATE
- **Implement**: Document regex-only PII over Presidio. Context: Presidio + PT-BR NER would cost ~2-3h of the 2-day MVP. Bidirectional PII blocking is mandatory. Decision: 4 regex patterns (email, telefone, CPF formatado, cartão 16 dígitos) in shared `_pii_patterns.py`, applied to input and output. Consequences: <1ms, zero dependency, deterministic; lost checksum validation, NER for names/addresses, unformatted CPF detection, CNPJ.
- **Mirror**: Same format.
- **Validate**: Word count < 300.

### Task 6: Create ADR 006

- **File**: `adr/006-local-embeddings.md`
- **Action**: CREATE
- **Implement**: Document sentence-transformers over Voyage AI. Context: Voyage requires API key/quota on the critical demo path. Decision: local `intfloat/multilingual-e5-small` (~120MB CPU) with `query:` / `passage:` prefix handling hidden in adapter. Consequences: demo works offline, no quota risk; lower PT-BR quality than Voyage-3, ~120MB container overhead.
- **Mirror**: Same format.
- **Validate**: Word count < 300.

### Task 7: Apply LIMITATIONS.md refinements

- **File**: `LIMITATIONS.md`
- **Action**: UPDATE (patch edits)
- **Implement**:
  1. Add new section `## Toxicity Validator` after introduction. Include: false positives on banking jargon ("morrer de rir"), PT-BR data sparsity in detoxify training, English-centric bias.
  2. Add new section `## Infrastructure & Scaling`. Include: single uvicorn worker (~1.5GB models, no duplication), no auth, no rate limiting, no horizontal scaling, no HTTPS/TLS termination.
  3. Add `<!-- Measured: 2026-05-25 -->` comment inside the jailbreak metrics table.
  4. Add `### Accepted Risks` subsection under Compliance, separating deliberate trade-offs (reasoning truncation to 200 chars, closed-loop fixtures) from confirmed gaps.
- **Mirror**: Follow existing table format (Gap | Impact).
- **Validate**: `grep -c "## " LIMITATIONS.md` should show ≥6 sections. `grep "Measured:" LIMITATIONS.md` should find the date-stamp.

### Task 8: Overhaul README.md

- **File**: `README.md`
- **Action**: UPDATE (complete rewrite, ~250 lines)
- **Implement**: New structure:
  1. **Badges** (CI, Python 3.12, Docker)
  2. **What is this?** (2 sentences + stack rationale hook)
  3. **Tech Stack** (table: FastAPI, LangGraph, Anthropic, Qdrant, Streamlit, detoxify, DeBERTa)
  4. **Architecture** (keep ASCII, update labels if needed)
  5. **Guardrails & Compliance** (keep validators table + R1-R5)
  6. **🎬 8-Minute Live Demo** (storyboard with copy-paste curls):
     - Beat 1: Happy path — `Como funciona o cartão Gold?`
     - Beat 2: Jailbreak DAN — blocked by layered defense
     - Beat 3: PII CPF — blocked by regex input guard
     - Beat 4: Compliance R2 — innocent question → plausible but non-compliant answer blocked by Haiku judge
  7. **Quick Start** (keep docker compose, add `~1.5 GB RAM` warning)
  8. **Running Tests** (`pytest -m "not slow and not network"`, `pytest -m adversarial`, block-rate ≥80% threshold)
  9. **Observability** (`docker logs api | jq`, latency breakdown, structlog JSON)
  10. **Project Layout** (keep tree, add `adr/`)
  11. **Design Docs & Decisions** (links to CLAUDE.md, LIMITATIONS.md, `adr/`)
  12. **Roadmap** (top 3 Extras: Presidio, Langfuse, AWS Bedrock)
- **Mirror**: Keep existing good sections (architecture diagram, validators table, response shape). Add new sections inline.
- **Validate**: `wc -l README.md` should be 200-280 lines. Must contain all 4 Beats. Must contain `docker compose up`. Must contain `pytest`.

---

## Validation

```bash
# Verify ADR directory exists and has 6 files
ls adr/001-* adr/002-* adr/003-* adr/004-* adr/005-* adr/006-*

# Verify word count per ADR (should be <300 words each)
for f in adr/*.md; do echo "$f: $(wc -w < $f) words"; done

# Verify README has key sections
grep -c "## " README.md  # should be ≥10
grep -q "Beat 1" README.md && echo "Beat 1 OK"
grep -q "Beat 2" README.md && echo "Beat 2 OK"
grep -q "Beat 3" README.md && echo "Beat 3 OK"
grep -q "Beat 4" README.md && echo "Beat 4 OK"
grep -q "docker compose up" README.md && echo "Quick start OK"
grep -q "pytest" README.md && echo "Tests section OK"
grep -q "jq" README.md && echo "Observability OK"
grep -q "adr/" README.md && echo "ADR link OK"

# Verify LIMITATIONS has new sections
grep -q "## Toxicity Validator" LIMITATIONS.md && echo "Toxicity section OK"
grep -q "## Infrastructure & Scaling" LIMITATIONS.md && echo "Infra section OK"
grep -q "Measured: 2026-05-25" LIMITATIONS.md && echo "Date-stamp OK"
grep -q "Accepted Risks" LIMITATIONS.md && echo "Accepted risks OK"

# Ruff (docs are markdown, but ensure no trailing issues)
ruff check . --select E,W
```

---

## Acceptance Criteria

- [ ] All 6 ADRs created in `adr/` with <300 words each
- [ ] README.md overhauled with 8-minute demo storyboard (Beats 1-4)
- [ ] README.md includes CI mention, test commands, observability narrative, ~1.5GB memory warning
- [ ] LIMITATIONS.md has ≥8 confirmed gaps (already satisfied — verify new sections added)
- [ ] LIMITATIONS.md has toxicity section, infra/scaling section, date-stamped metrics table, accepted risks subsection
- [ ] All files follow existing naming conventions
- [ ] `ruff check .` passes (no Python code changed, but good hygiene)
- [ ] Commit message references SCRUM-15
- [ ] Jira issue SCRUM-15 moved to Done with summary comment
