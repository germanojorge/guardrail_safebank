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

Two-layer prompt injection detector: a substring fast-path (<5ms) checks for ~20
known jailbreak keywords in PT-BR and English; paraphrased attacks that bypass the
keyword list fall through to a DeBERTa classifier
(`protectai/deberta-v3-base-prompt-injection-v2`, <300ms CPU). Either layer
blocking produces `passed=False` with `details["layer_caught"]` set to `"substring"`
or `"deberta"` for attribution.

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **Substring list is finite and public** | Any attacker who reads the source code (or this doc) can craft prompts that bypass Layer 1 by avoiding all listed keywords |
| **DeBERTa trained on English-dominant data** | PT-BR paraphrasing with no English keywords may have lower recall; not measured at MVP scope |
| **No multilingual DeBERTa available for injection** | `protectai/deberta-v3-base-prompt-injection-v2` is English-trained; PT-BR bypass rate unknown until SCRUM-11 adversarial suite runs |
| **Encoding bypasses (base64, leetspeak, unicode lookalikes)** | Neither layer catches encoded attacks; marked as xfail in `KNOWN_BYPASSES` fixtures |
| **Context-smuggling (code block, JSON fields)** | Jailbreak embedded in code blocks or structured fields bypasses both layers; marked as xfail |
| **False positive: "ja" substring** | Words like `"finja"`, `"aja"` contain the substring `"ja"` — not a keyword, but similar PT-BR false-positive patterns may exist |

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
> from JailbreakBench v1.0 (MIT). Run `uv run python scripts/measure_jailbreak_layers.py`
> to refresh after fixture changes.


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
