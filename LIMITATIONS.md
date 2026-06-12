# Known Limitations

This document lists what each guardrail reliably misses — not hypothetical edge cases, but confirmed classes of bypass or false-negative. Maintained per `building-rigorously.md §7`.

Each section is owned by the validator that introduces it; future validators append their own section.

---

## Toxicity Validator (`guardrails/validators/toxic.py`)

### What it does

Uses `detoxify` with the `multilingual` XLM-RoBERTa model to classify text as toxic. Applied to both input and output. Threshold is tuned for banking chatbot tolerance (mild profanity may pass, hate speech is blocked).

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **False positives on banking jargon** | Phrases like "morrer de rir" (laugh to death) or "matar a curiosidade" (kill the curiosity) can trigger toxicity flags due to literal keyword matches in an English-centric model. |
| **PT-BR data sparsity in detoxify training** | The `multilingual` model is trained primarily on English toxicity datasets with limited PT-BR coverage. Sarcasm, regional slurs, and cultural context are poorly captured. |
| **English-centric bias** | The model may under-detect PT-BR toxic content while over-detecting benign PT-BR colloquialisms that happen to contain English-toxic substrings. |

---

## PII Validator (`guardrails/validators/pii.py`)

### What it does

Regex-only detection for four PT-BR PII categories: `email`, `telefone`, `cpf`, `cartao`. Detection only — MVP blocks on any match; masking is listed in Extras (CLAUDE.md).

### Closed gaps (2026-05-27)

| Gap (closed) | Fix |
|---|---|
| **No CPF checksum** | Módulo 11 implemented in `_pii_patterns._validate_cpf`; invalid CPFs (`111.111.111-11`) no longer produce false positives. |
| **CPF unformatted** | `cpf_raw` pattern (`\d{11}`) added; checksum validation filters out non-CPF sequences. `12345678909` now detected. |
| **No Luhn validation for cards** | Luhn implemented in `_pii_patterns._validate_luhn`; 16-digit sequences that fail Luhn are dropped. `1234-5678-9012-3456` no longer triggers a block. |
| **No CNPJ** | CNPJ pattern (`\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}`) + checksum validator added. |
| **Phone regex misses PT-BR formats** | Regex updated: covers `(11) 91234-5678`, `11 91234-5678`, `+55 11 91234-5678`, and unformatted mobile `11912345678`. `(?<!\d)` guards prevent false positives inside card/CPF sequences. |

### Confirmed gaps (remaining)

| Gap | Impact |
|-----|--------|
| **No conta bancária** | Bank account numbers (agência + conta) are not detected. |
| ~~**No NER (names, addresses)**~~ | **Closed 2026-05-27** — Presidio Analyzer + spaCy `pt_core_news_sm` added as Layer 2. Detects PERSON and LOCATION. Quality caveat: `sm` model has lower NER recall than `lg`; ambiguous first names may be missed. |
| **Phone 9-digit local (no DDD)** | `912345678` without area code is not detected — ambiguous without DDD context (could be order number, etc.). |
| **Email regex is RFC-naive** | Under-matches unicode TLDs. May over-match inside code blocks or markdown URLs. |
| **CNPJ unformatted** | Only formatted CNPJ (`00.000.000/0000-00`) is detected; bare 14-digit sequences are not. |

### Fixture closed-loop caveat

The PII test fixtures (`tests/fixtures/pii_samples.py` and `tests/adversarial/fixtures/pii_handcrafted.jsonl`) were hand-crafted by the same agent that wrote the regex patterns. They demonstrate **pattern coverage** (each entity type is exercised), not **adversarial breadth**. No external PT-BR PII corpus was available at MVP scope. Per `building-rigorously.md §1`, these tests validate internal consistency, not correctness against real-world data distributions.

### Roadmap (Extras)

Per CLAUDE.md Extras table:
- **Presidio Analyzer** with PT-BR NER models — adds name/address detection
- **CNPJ unformatted** (14 plain digits + checksum)
- **PII masking** instead of hard block — better UX, same security guarantee

---

## Jailbreak Validator (`guardrails/validators/jailbreak.py`)

### What it does

Four-layer prompt injection detector with early-exit, ordered from cheapest to most expensive:

| Layer | Name | Tech | Latency | What it catches |
|-------|------|------|---------|-----------------|
| L1a | Regex Fast-Path Gate | Named regex rules (PT-BR/EN) | <1ms | Bigram patterns: "aja como", "DAN mode", "ignore instructions", "jailbreak", etc. |
| L1b | POS Tagger | `Emanuel/porttagger-news-base` + spaCy `pt_core_news_lg` word vectors | ~20-40ms CPU | Imperative VERB patterns with cosine similarity to reference centroids |
| L1c | Semantic Index | `paraphrase-multilingual-MiniLM-L12-v2` + pre-computed Necent embeddings | ~10ms CPU | Paraphrased jailbreak prompts that evade deterministic layers |
| L2 | Prompt-Guard-2 | `meta-llama/Llama-Prompt-Guard-2-86M` (multilingual, incl. PT-BR) | <300ms CPU | Anything that survived L1a–L1c |

Either layer blocking produces `passed=False` with `details["layer_caught"]` set to `"regex"`, `"pos_tagger"`, `"semantic"`, or `"prompt_guard"` for attribution.

> **2026-05-27 model change:** the previous `protectai/deberta-v3-base-prompt-injection-v2`
> was English-centric and classified benign PT-BR banking phrases as INJECTION with ~1.0
> confidence. Replaced with Meta Prompt-Guard-2 (multilingual, gated repo — needs HF token).
>
> **2026-05-28 architecture upgrade:** expanded from 2 to 4 layers. POS tagger (L1b) catches
> PT-BR imperatives with morphosyntactic precision. Semantic index (L1c) catches paraphrased
> social-engineering attacks. Both layers are fail-open (errors fall through to next layer).

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **POS tagger depends on spaCy pt_core_news_lg** | ~500MB model loaded at startup. Word vectors cover ~500k forms but may miss neologisms, slang, or domain-specific verbs. Adds ~20-40ms latency to path that regex misses. |
| **Semantic index depends on dataset gated `Necent`** | Maximum quality requires HuggingFace access. Fallback index from open-source datasets has lower recall. Threshold 0.80 may let through paraphrases very distant from the index. |
| **Substring/Regex list is finite and public** | Any attacker who reads the source code (or this doc) can craft prompts that bypass Layer 1a by avoiding all listed keywords |
| **PT-BR recall not exhaustively measured** | Prompt-Guard-2 is multilingual and fixed the EN-centric false positives, but PT-BR *recall* on paraphrased attacks is only spot-checked, not yet run against a full adversarial suite |
| **Encoding bypasses (base64, leetspeak, unicode lookalikes)** | No layer catches encoded attacks; marked as xfail in `KNOWN_BYPASSES` fixtures |
| **Context-smuggling (code block, JSON fields)** | Jailbreak embedded in code blocks or structured fields bypasses all layers; marked as xfail |

### Layered-defense comparison (JailbreakBench external fixtures)

<!-- BEGIN: jailbreak-layer-metrics -->
<!-- Measured: 2026-05-25 -->
| Layer | EN block rate | PT-BR block rate | Overall |
|-------|---------------|------------------|---------|
| Substring only | 7/10 (70%) | 3/12 (25%) | 10/22 (45%) |
| Substring + DeBERTa | 10/10 (100%) | 12/12 (100%) | 22/22 (100%) |

<!-- END: jailbreak-layer-metrics -->

> Table populated by `scripts/measure_jailbreak_layers.py` (SCRUM-10). Metrics
> measured against `tests/adversarial/fixtures/jailbreak_external.jsonl` sourced
> from JailbreakBench v1.0 (MIT). Updated measurements with POS + Semantic layers
> pending SCRUM-11 adversarial suite rerun.


---
## Out-of-Scope Validator (`guardrails/validators/out_of_scope.py`)

### What it does

Blocks non-banking queries using seed-based cosine similarity. Embeds the input text
with `paraphrase-multilingual-MiniLM-L12-v2` and compares against:

- **In-scope seeds** (~30 banking questions from Itaú FAQ + hand-crafted)
- **Out-of-scope seeds** (~30 generic non-banking topics)

Blocks if: `max_in < threshold_in (0.40) AND max_out > threshold_out (0.50)`,
OR `max_out > max_in + margin (0.15)`. The second condition handles ambiguous
queries where both similarities are moderate but out-of-scope wins.

Applied last in `input_guard` (after jailbreak) — scope is not a security threat,
so higher-priority validators check first.

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **Zero-shot similarity, not fine-tuned** | Model was never trained on banking vs non-banking classification. Seed-based cosine similarity is a heuristic, not a classifier. |
| **Seed coverage is limited** | 30 in-scope seeds can't cover all possible banking queries. Creative rephrasings may have low in-scope similarity and trigger false positives. |
| **Out-of-scope seeds are hand-crafted** | The 30 out-of-scope topics are not comprehensive. Novel non-banking topics (e.g., niche hobbies) may not match any seed and pass through. |
| **No learning from blocks** | Each request is independent; no feedback loop to improve seed coverage over time. |
| **False positives for borderline queries** | Mixed questions (e.g., "posso pagar boleto do restaurante pelo app?") may be incorrectly blocked if out-of-scope similarity dominates. |


---
## Compliance Judge (`guardrails/validators/compliance.py`)

### What it does

LLM-as-Judge using Claude Haiku 4.5 with `tool_use` for structured verdict output (`{verdict, rule_violated, reasoning}`) against a 5-rule banking compliance rubric (R1–R5: promessa de rendimento, recomendação financeira, falsa execução, vazamento de instruções, fora de escopo). Applied only on output — client questions never violate compliance.

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **Fixture closed-loop** | Rubrica + fixtures + judge escritos pelo mesmo agente. Testes validam operacionalização contra rubrica DECLARADA, não correção contra mundo real. |
| **Sem annotator independente** | Fixtures hand-crafted pelo mesmo autor da rubrica — risco de seleção viesada para casos que o judge acerta. |
| **Sensibilidade a rephrasings** | Beat 4 testado em 1 fraseamento. Variações ("Qual o melhor CDB pra mim?", "Me recomende um investimento") não medidas no MVP. |
| **Sem histórico de conversa** | Judge vê só última resposta — perde correlações temporais (ex.: pressão progressiva sobre o chatbot). |

### Accepted Risks

These are deliberate trade-offs, not unknown gaps:

| Risk | Rationale |
|------|-----------|
| **Custo por chamada (~$0.0001/req)** | Haiku is the cheapest Claude model. Prompt caching reduces cost further. Rate limiting is deferred to Extras. |
| **Sem reask em fail** | Bloqueio direto maximiza previsibilidade na demo. Reask 1x com auto-correção é Extras. |
| **Reasoning truncado em 200 chars** | Reduces PII blast radius in observability logs. Full reasoning available in Anthropic dashboard for debugging. |

### Fixture closed-loop caveat

The Compliance adversarial fixture (`tests/adversarial/fixtures/compliance_handcrafted.jsonl`) is **closed-loop** per `building-rigorously.md §1`: the rubric, the fixtures, and the judge were all authored by the same agent. Each fixture entry carries `"closed_loop": true` and a rationale header documents the limitation. These tests validate that the judge **operationalises the declared rubric**, not correctness against an external standard. Independent annotation (Cohen's kappa, ~100 cases) is listed in Extras (CLAUDE.md).

### Roadmap (Extras)

- Annotator independente para validação cruzada das fixtures
- Paraphrasing dataset (variações do Beat 4 e demais violações)
- Histórico de conversa (janela deslizante de N turnos)
- Calibração contra labels humanos (Cohen's kappa, ~100 casos)
- Reask 1x com auto-correção do output


---

## Adversarial Suite Block Rates (SCRUM-10)

Aggregate block rates from `tests/adversarial/` measured against external-source plus
hand-crafted fixtures. Rates are computed by the session-finalizer in `conftest.py` and
printed at the end of each adversarial test run.

| Category | Fixture | Source | Samples | Block rate |
|----------|---------|--------|---------|------------|
| Jailbreak | `jailbreak_external.jsonl` | JailbreakBench v1.0 (MIT) + translated PT-BR | 22 (12 PT-BR, 10 EN) | Run `pytest -m adversarial -k jailbreak` |
| Toxicity | `toxic_external.jsonl` | HateBR (CC BY-NC 4.0) + RealToxicityPrompts (CC-BY 4.0) | 22 (12 PT-BR, 10 EN) | Run `pytest -m adversarial -k toxic` |
| PII | `pii_handcrafted.jsonl` | Hand-crafted (closed-loop) | 19 | Run `pytest -m adversarial -k pii` |
| Compliance | `compliance_handcrafted.jsonl` | Hand-crafted (closed-loop) | 19 | Run `pytest -m adversarial -k compliance -m network` |

### Block-rate threshold

Per `building-rigorously.md §3`: the acceptance threshold is **≥80%** on jailbreak and
toxicity categories. If the first run is below this threshold, investigate and document
the gap — do not lower the threshold.

### Offline vs network split

| Marker | Scope | CI run |
|--------|-------|--------|
| `adversarial and not network` | Jailbreak, Toxic, PII (no API calls) | Yes |
| `adversarial and network` | Compliance (requires Anthropic API key) | Manual only |

---

## Retrieval System (RAG) — `guardrails/pipeline/nodes.py`, `guardrails/adapters/`

### What it does

Dense semantic retrieval: `intfloat/multilingual-e5-base` encodes the query → Qdrant cosine search → optional score threshold filter → optional cross-encoder reranker → top-3 chunks passed to the LLM. Optional components are configured in `config.yaml` under `retrieval.*`.

### SCRUM-39 measurements (faq_bacen split, 373 queries, 1678 corpus docs)

Anti-tautology gate: `run_eval_manual` dense-only recall@3 = 0.6756 matches `InformationRetrievalEvaluator` recall@3 = 0.6756 exactly — confirming the manual eval path is not tautological.

**Before/after table — see `models/eval/retrieval_before_after.md` for full data.**

<!-- BEGIN: retrieval-before-after -->
<!-- Measured: 2026-06-12 (SCRUM-39) -->
| Configuration | recall@3 | mrr@10 | ndcg@10 | Note |
|---------------|----------|--------|---------|------|
| Dense only (e5-base, top-3) | 0.6756 | 0.5648 | 0.5932 | baseline |
| Dense-20 + CE reranker (top-3) | **0.6836** | **0.6230** | **0.6668** | +1.2pp / +10.3pp / +12.4pp |
<!-- END: retrieval-before-after -->

<!-- BEGIN: threshold-sweep -->
<!-- Measured: 2026-06-12 (SCRUM-39) -->
| Threshold | recall@3 (in-scope) | off-topic rejection % | Note |
|-----------|--------------------|-----------------------|------|
| 0.70 | 0.6756 | 0.0% | — |
| 0.78 | 0.6756 | 10.0% | — |
| **0.82** | **0.6756** | **65.0%** | selected |
| 0.84 | 0.6729 | 100.0% | — |
| 0.88 | 0.4263 | 100.0% | recall cliff |
<!-- END: threshold-sweep -->

### Config decisions (SCRUM-39)

**Score threshold**: `retrieval.score_threshold: 0.82` — 65% off-topic rejection with zero recall@3 cost. See sweep table above.

**Reranker**: `retrieval.reranker.enabled: true` — +1.2pp recall@3, +10.3pp mrr@10, +12.4pp ndcg@10. Model: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`. Full before/after in `models/eval/retrieval_before_after.md`.

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **Score threshold applies only to dense cosine score** | A document that barely clears the threshold due to vocabulary overlap may still be irrelevant. Threshold prevents out-of-domain retrievals but does not guarantee relevance. |
| **Cross-encoder is English/multilingual but not fine-tuned on PT-BR banking** | `mmarco-mMiniLMv2-L12-H384-v1` was trained on MS MARCO. Banking-specific terminology may not rerank optimally. |
| **Single-hop retrieval only** | Multi-hop questions ("qual a taxa do produto que mencionou no mês passado?") require multi-hop RAG, not implemented. |
| **No groundedness judge** | Retrieved chunks are passed to the LLM but not verified post-generation for hallucination. Groundedness judge is listed in Extras (CLAUDE.md). |
| **In-memory eval vs Qdrant production** | `run_eval_manual` uses numpy cosine directly; production goes through Qdrant. Minor score differences due to HNSW approximation may exist but are not currently measured. |

---

## Infrastructure & Scaling

### What it is

The MVP is designed for local Docker demonstration, not production deployment.

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **Single uvicorn worker** | ~1.5GB of model weights (DeBERTa + detoxify + sentence-transformers) are loaded into memory. Multiple workers would duplicate this footprint. Single worker means no request-level parallelism within the process. |
| **No authentication** | Anyone with network access to `localhost:8000` can query the API and consume Anthropic quota. |
| **No rate limiting** | A misconfigured client or malicious script can exhaust API keys or degrade the single worker. |
| **No horizontal scaling** | No load balancer, no auto-scaling, no health-based traffic shifting. Docker Compose is single-node by design. |
| **No HTTPS / TLS termination** | All traffic is plain HTTP. In production this must terminate at a reverse proxy (nginx, Traefik, AWS ALB). |
| **No persistent block log storage** | Block events are JSON-structured stdout only. No database, no SIEM integration, no retention policy. |
| **No secret management** | `ANTHROPIC_API_KEY` is passed via environment variable. No Vault, no AWS Secrets Manager, no key rotation. |
