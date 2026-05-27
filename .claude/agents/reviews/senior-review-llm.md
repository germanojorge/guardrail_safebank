# LLM-Consumable Review Report

```yaml
meta:
  project: guardrail-safebank
  repo_path: /home/germano/Projects/guardrail-safebank
  review_date: 2026-05-26
  scope: full_repository
  context:
    purpose: "Bidirectional LLM guardrail proxy for B2C banking chatbot (PT-BR)"
    deadline_constraint: "2-day MVP for technical interview"
    stack: [LangGraph, FastAPI, Anthropic Claude, Qdrant, sentence-transformers, structlog, Streamlit, Docker]
    validators: [toxic (detoxify), pii (regex PT-BR), jailbreak (substring + DeBERTa), compliance (Claude Haiku judge + R1-R5 rubric)]
  reviewer_role: senior_ai_engineer
  recommendation: APPROVED_WITH_RESERVATIONS
  confidence: high
  ship_blocking_issue_count: 3

validation:
  ruff_check: pass
  ruff_format: pass
  pytest_fast: { passed: 76, xfail: 3, failed: 0, note: "xfail aligned with LIMITATIONS.md" }
  pytest_adversarial: not_run_in_review
  pytest_slow: not_run_in_review

issues:
  - id: C1
    severity: critical
    category: fail_closed_violation
    title: "ToxicValidator has no exception handling around model.predict"
    file: guardrails/validators/toxic.py
    lines: "38-55"
    evidence: "self._model.predict(text) called with no try/except wrapper"
    impact: "OOM, CUDA/device mismatch, or model corruption → uncaught exception → HTTP 500. Input guard becomes fail-OPEN in functional sense (request dies instead of blocking)."
    repro: "Force detoxify to raise (e.g., monkeypatch _model.predict to raise RuntimeError) and POST /chat — request 500s instead of returning a block"
    fix: |
      Wrap predict in try/except; on failure return:
      ValidatorResult(passed=False, score=1.0, details={"error": type(e).__name__, "stage": "toxic_predict"})
      Mirror the pattern already used in ComplianceValidator (compliance.py:119-133).
    estimated_effort_minutes: 30
    test_required: "tests/unit/test_toxic.py::test_fail_closed_on_model_exception (monkeypatch _model.predict)"
    blocks_ship: true

  - id: C2
    severity: critical
    category: fail_closed_violation
    title: "JailbreakValidator has no exception handling around DeBERTa pipeline call"
    file: guardrails/validators/jailbreak.py
    lines: "126-128"
    evidence: "self._pipeline(text)[0] called bare"
    impact: "DeBERTa model (~500MB) may fail to load/infer in production (cold start, CUDA mismatch, HF cache miss). Exception crashes the request."
    repro: "Monkeypatch self._pipeline to raise; POST /chat → 500"
    fix: "Wrap pipeline call in try/except, return fail-closed ValidatorResult with score=1.0 and error metadata. Substring fast-path layer can stay as primary signal but must not be relied on as sole protection when DeBERTa errors."
    estimated_effort_minutes: 30
    test_required: "tests/unit/test_jailbreak.py::test_fail_closed_on_pipeline_exception"
    blocks_ship: true

  - id: C3
    severity: critical
    category: fail_closed_violation
    title: "ComplianceValidator tool_use parsing raises StopIteration before fail-closed handler"
    file: guardrails/validators/compliance.py
    lines: "99"
    evidence: 'tool_block = next(b for b in response.content if b.type == "tool_use")'
    impact: |
      If Claude returns stop_reason="end_turn" without using the declared tool (model divergence, prompt drift, content policy refusal), next() raises StopIteration.
      The except block at line 119 catches Anthropic API exceptions but does NOT catch StopIteration — the request crashes uncaught.
      This is the MOST CRITICAL of the three because Compliance is the load-bearing judge for the banking domain (R1-R5 rubric).
    repro: "Mock AnthropicProvider.complete_with_tools to return a Message with no tool_use block — call ComplianceValidator.validate() → StopIteration propagates"
    fix: |
      Replace with: tool_block = next((b for b in response.content if b.type == "tool_use"), None)
      Then check: if tool_block is None: return ValidatorResult(passed=False, score=1.0, details={"error": "judge_no_tool_use"})
    estimated_effort_minutes: 20
    test_required: "tests/unit/test_compliance.py::test_fail_closed_when_judge_omits_tool_use"
    blocks_ship: true

  - id: M1
    severity: medium
    category: api_contract
    title: "HTTP 200 for policy blocks is undocumented in OpenAPI schema"
    file: guardrails/api/app.py
    lines: "104-140"
    evidence: "CLAUDE.md declares 'block = HTTP 200 (policy decision)' but FastAPI response_model does not signal block vs allow at HTTP-status level"
    impact: "Downstream integrators reading 200 as success may not branch on the block field in the JSON body. Silent policy bypass risk."
    fix: "Either document explicitly in route docstring + OpenAPI examples, or return HTTP 403 for blocks (more semantically correct for policy denial)."
    blocks_ship: false

  - id: M2
    severity: medium
    category: operational_readiness
    title: "Lifespan does not validate ML model load; /health returns 200 even when models failed"
    file: guardrails/api/app.py
    lines: "76-87"
    impact: "App can boot in broken state. /health green but /chat 500s on first request. Hard to diagnose in container orchestration."
    fix: "In lifespan, run a 1-char inference through each validator (toxic, jailbreak, embedding). Fail startup loudly if any returns exception."
    blocks_ship: false

  - id: M3
    severity: medium
    category: detection_quality
    title: "PII regex accepts invalid CPF (no Modulo-11 checksum) and invalid card (no Luhn)"
    file: guardrails/_pii_patterns.py
    lines: "15-16"
    declared_in_limitations: true
    impact: "False positives on patterns that look like CPF/card but aren't (e.g., 000.000.000-00 in docs). In banking context this is non-trivial."
    fix: "Add validate_cpf_checksum() and luhn_check() — both are <15 LOC each in Python. Already in Extras backlog."
    blocks_ship: false

  - id: M4
    severity: medium
    category: detection_quality
    title: "DeBERTa model is English-trained; PT-BR adversarial coverage is statistically weak"
    files: [LIMITATIONS.md, tests/adversarial/fixtures/jailbreak_external.jsonl]
    evidence: "protectai/deberta-v3-base-prompt-injection-v2 is EN-dominant; PT-BR dataset N=12 translated samples"
    impact: "Reported 12/12 PT-BR block rate is misleading at small N. Production PT-BR bypass rate is unknown."
    fix: "Either add PT-BR-native jailbreak dataset, OR explicitly bound the claim in LIMITATIONS.md to 'measured on translated JailbreakBench subset, N=12, not native PT-BR adversarial.'"
    blocks_ship: false

  - id: M5
    severity: medium
    category: test_methodology
    title: "Compliance and PII fixtures are hand-crafted by the same author as the rubric/regex (closed validation loop)"
    files: [tests/adversarial/fixtures/compliance_handcrafted.jsonl, tests/adversarial/fixtures/pii_handcrafted.jsonl]
    declared_in_limitations: true
    references_rule: "building-rigorously.md §1"
    impact: "Tests validate implementation-spec consistency, not real-world correctness. Cannot claim detection rate on these validators."
    fix: "Cohen's kappa against ~100 human-labeled examples (already in Extras backlog). Until then, do not present numerical detection rates for compliance/PII as evidence of effectiveness."
    blocks_ship: false

  - id: M6
    severity: medium
    category: operational_readiness
    title: "docker-compose uses depends_on: service_started, not service_healthy"
    file: docker-compose.yml
    lines: "15-17"
    impact: "API container can start before Qdrant is ready to accept connections. Demo can fail silently on first /chat."
    fix: "Add healthcheck to qdrant service + depends_on: condition: service_healthy on api"
    blocks_ship: false

  - id: M7
    severity: medium
    category: detection_quality
    title: "Compliance judge has no conversation history and is sensitive to rephrasing"
    file: guardrails/validators/compliance.py
    lines: "63"
    declared_in_limitations: true
    impact: "Demo Beat 4 measured on one specific phrasing only. Production users will rephrase; judge consistency on paraphrases is unknown."
    fix: "Add multi-phrasing test sweep (Extras: reask 1x + last-N-turn context)."
    blocks_ship: false

  - id: L1
    severity: low
    category: defensive_coding
    file: guardrails/pipeline/nodes.py
    lines: "96-106"
    note: "retrieve node wraps embedding.embed_queries in try/except but not vector_store.search"

  - id: L2
    severity: low
    category: feature_scope
    file: guardrails/pipeline/nodes.py
    lines: "188-189"
    note: "block_log node only emits to structlog; no DB persistence (declared, Extras)"

  - id: L3
    severity: low
    category: config_exposure
    file: guardrails/validators/compliance.py
    lines: "51"
    note: "Compliance timeout hardcoded to 5s; not exposed in config.yaml"

  - id: L4
    severity: low
    category: config_exposure
    file: guardrails/adapters/embedding.py
    lines: "32"
    note: "batch_size=32 hardcoded"

  - id: L5
    severity: low
    category: api_contract
    file: guardrails/adapters/embedding.py
    note: "E5 'query:'/'passage:' prefix requirement is in docstring but not enforced/documented in the Protocol — alternative implementers may forget"

  - id: L6
    severity: low
    category: noise
    note: "torch JIT script DeprecationWarning surfaces in pytest output"

positives:
  architecture:
    - { file: "guardrails/validators/compliance.py:119-133", finding: "Anthropic API exception → ValidatorResult(passed=False, score=1.0) — correct fail-closed" }
    - { file: "guardrails/pipeline/nodes.py:96-106", finding: "RAG degrades gracefully on embedding/vector failure instead of propagating" }
    - { file: "guardrails/adapters/llm.py:84-85,115-118", finding: "complete() and complete_with_tools() return safe defaults on exception" }
    - { file: "guardrails/api/app.py:94-102", finding: "request_id contextvar bound on entry, cleared in finally — no cross-request leak" }
    - { file: "guardrails/validators/jailbreak.py:91-158", finding: "Layered defense correctly ordered (substring fast-path before DeBERTa)" }
    - { file: "guardrails/pipeline/graph.py", finding: "StateGraph: 5 nodes, conditional edges after input/output guards, no orphans" }
    - { file: "guardrails/adapters/*.py", finding: "@runtime_checkable Protocols make Bedrock-swap narrative credible" }
    - { file: "guardrails/validators/compliance.py:90, guardrails/adapters/llm.py:79", finding: "cache_control: ephemeral on system prompt — ready for prompt caching" }
  observability:
    - { file: "guardrails/observability/logger.py", finding: "PII sanitization before logging, request hash for forensics, per-validator latency capture" }
  configuration:
    - { file: "guardrails/config.py:14", finding: "${ENV_VAR} expansion — no hardcoded secrets" }
  testing:
    - { finding: "76 passing + 3 declared xfail aligned with LIMITATIONS.md" }
    - { finding: "Jailbreak fixtures from JailbreakBench (MIT); Toxic from HateBR + RealToxicityPrompts — external sources, not tautological" }
  documentation:
    - { file: "LIMITATIONS.md", finding: "Confirmed (not hypothetical) gaps per validator; closed_loop flag in fixture JSONLs — exemplary honesty" }
    - { file: "adr/00{1..6}-*.md", finding: "Each pivot decision (drop guardrails-ai, drop Presidio, drop Voyage, drop Langfuse) has its own ADR with trade-off explicit" }
    - { file: "CLAUDE.md", finding: "Decision table with dates — full traceability" }
  quality:
    - { finding: "ruff check + ruff format: 0 warnings across 66 files" }

building_rigorously_audit:
  - rule: "§1 closed validation loop"
    status: partial
    detail: "Jailbreak/Toxic use external fixtures (good). Compliance/PII hand-crafted, but explicitly flagged in LIMITATIONS.md."
  - rule: "§3 100% green is a warning"
    status: needs_attention
    detail: "76/76 pass, but mostly unit tests with mocks. Adversarial sample size small (~22 PT-BR jailbreak). More red-teaming would raise confidence."
  - rule: "§4 doc drift"
    status: clean
    detail: "CLAUDE.md, ADRs, LIMITATIONS.md observed consistent with code."
  - rule: "§6 substring matching is not a guardrail"
    status: respected
    detail: "Substring is explicit fast-path, layered with DeBERTa — not the sole detection."
  - rule: "§7 declare limitations"
    status: exemplary
    detail: "LIMITATIONS.md lists confirmed (not hypothetical) failure classes per validator."
  - rule: "§8 artifact volume ≠ rigor"
    status: balanced
    detail: "ADRs concise; LIMITATIONS.md verifiable items."

risk_summary:
  most_likely_interview_attack_vector: "What happens if Detoxify/DeBERTa model raises mid-request?"
  current_answer: "Request crashes (fail-OPEN functionally)"
  required_answer_after_fix: "Validator returns fail-closed ValidatorResult; pipeline blocks request and logs structured error"
  fix_total_effort_minutes: 80

handoff_actions:
  before_demo:
    - "Apply fixes C1, C2, C3 (~80min total)"
    - "Add unit tests for the three fail-closed paths"
    - "Re-run pytest, confirm green"
  optional_polish:
    - "Add Qdrant healthcheck (M6) — 10min"
    - "Document HTTP 200 block semantics in OpenAPI (M1) — 15min"
    - "Add lifespan model-load smoke test (M2) — 30min"
  narrative_prep:
    - "Be ready to talk about ADR rationale for each pivot (guardrails-ai, Presidio, Voyage, Langfuse)"
    - "Be ready to defend closed-loop fixture choice for Compliance/PII (point to LIMITATIONS.md and Cohen's kappa as planned mitigation)"
    - "Be ready to discuss multi-provider Protocol → Bedrock swap path"

machine_actionable_diff_hints:
  C1:
    file: guardrails/validators/toxic.py
    pattern: "raw self._model.predict call inside validate()"
    transform: "wrap in try/except Exception as e; return ValidatorResult(passed=False, score=1.0, details={'error': type(e).__name__})"
  C2:
    file: guardrails/validators/jailbreak.py
    pattern: "raw self._pipeline(text)[0] call"
    transform: "same wrap-and-fail-closed pattern"
  C3:
    file: guardrails/validators/compliance.py:99
    before: 'tool_block = next(b for b in response.content if b.type == "tool_use")'
    after: |
      tool_block = next((b for b in response.content if b.type == "tool_use"), None)
      if tool_block is None:
          return ValidatorResult(passed=False, score=1.0, details={"error": "judge_no_tool_use", "stop_reason": getattr(response, "stop_reason", None)})

final_verdict:
  decision: APPROVED_WITH_RESERVATIONS
  ship_for_interview: yes_after_critical_fixes
  estimated_fix_window: "~80 minutes for all 3 criticals + tests"
  strengths_to_highlight: [fail_closed_in_most_paths, external_adversarial_fixtures, honest_LIMITATIONS_md, protocol_based_adapters, structured_observability]
  weaknesses_to_preempt: [three_fail_closed_gaps_in_validators, undocumented_HTTP_200_block_semantics, weak_PT_BR_jailbreak_sample_size]
```
