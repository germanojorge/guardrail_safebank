# Known Limitations

This document lists what each guardrail reliably misses — not hypothetical edge cases, but confirmed classes of bypass or false-negative. Maintained per `building-rigorously.md §7`.

Each section is owned by the validator that introduces it; future validators append their own section.

---

## PII Validator (`guardrails/validators/pii.py`)

### What it does

Regex-only detection for four PT-BR PII categories: `email`, `telefone`, `cpf`, `cartao`. Detection only — MVP blocks on any match; masking is listed in Extras (CLAUDE.md).

### Confirmed gaps

| Gap | Impact |
|-----|--------|
| **No CPF checksum** | Accepts mathematically invalid CPFs like `000.000.000-00` and `123.456.789-00` (wrong check digits). A valid-format but invalid CPF produces a false positive block. |
| **No Luhn validation for cards** | Accepts invalid card numbers like `1111-1111-1111-1111`. Any 16-digit sequence in `DDDD-DDDD-DDDD-DDDD` or `DDDD DDDD DDDD DDDD` format triggers a block. |
| **CPF unformatted (11 plain digits)** | Pattern `\b\d{3}\.\d{3}\.\d{3}-\d{2}\b` requires dots and dash. `12345678909` (no punctuation, common user input) passes undetected. |
| **No CNPJ** | CNPJ numbers are not detected. |
| **No conta bancária** | Bank account numbers (agência + conta) are not detected. |
| **No NER (names, addresses)** | Person names, street addresses, and city/state are not detected. Presidio Analyzer with PT-BR NER models is the planned Extras path (see CLAUDE.md). |
| **Phone regex misses 11-digit mobile and 9-digit local** | Pattern `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` matches exactly 10-digit sequences (e.g., `011-912-3456`). Missing formats: 11-digit unformatted (`11912345678`), 9-digit local (`912345678`), parenthesized (`(11) 91234-5678`), international (`+55 11 91234-5678`). |
| **Phone false positives** | The phone regex can match 10-digit suffixes of CPF numbers or numeric dates embedded in text. Since patterns are checked independently, a CPF match also triggers a `cpf` block in the same call — no functional problem, but worth knowing. |
| **Email regex is RFC-naive** | Under-matches unicode TLDs (e.g., `.рф`, `.中文`). May over-match inside code blocks or markdown URLs where the surrounding word boundary does not apply. |
| **Card regex over-matches** | Any 16-digit sequence in groups of 4 (loyalty IDs, tracking codes, serial numbers) will trigger a block. Future Luhn validation would reduce false positives. |

### Layered-defense comparison (jailbreak — see Jailbreak Validator section below)

| Layer | Block rate on SUBSTRING_CAUGHT_SAMPLES | Block rate on DEBERTA_ONLY_SAMPLES |
|-------|----------------------------------------|------------------------------------|
| Substring only | 3/3 (100%) | 0/3 (0%) — these are designed to bypass it |
| Substring + DeBERTa | 3/3 (100%) | TBD — populated after SCRUM-11 adversarial suite |

### Fixture closed-loop caveat

The PII test fixtures (`tests/fixtures/pii_samples.py`) were hand-crafted by the same agent that wrote the regex patterns. They demonstrate **pattern coverage** (each of the 4 entity types is exercised), not **adversarial breadth**. No external PT-BR PII corpus was available at MVP scope. Per `building-rigorously.md §1`, these tests validate internal consistency, not correctness against real-world data distributions.

### Roadmap (Extras)

Per CLAUDE.md Extras table:
- **Presidio Analyzer** with PT-BR NER models — adds name/address detection
- **CPF checksum** (Módulo 11 algorithm) — eliminates valid-format/invalid-number false positives
- **CNPJ with checksum**
- **Luhn algorithm for cards** — reduces 16-digit sequence false positives
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

### Layered-defense comparison

| Layer | Block rate on SUBSTRING_CAUGHT_SAMPLES | Block rate on DEBERTA_ONLY_SAMPLES |
|-------|----------------------------------------|------------------------------------|
| Substring only | 3/3 (100%) | 0/3 (0%) — these are designed to bypass it |
| Substring + DeBERTa | 3/3 (100%) | TBD — populated after SCRUM-11 adversarial suite |

> Note: the DeBERTa column for DEBERTA_ONLY_SAMPLES will be populated by
> SCRUM-11 against the full JailbreakBench dataset. Current fixtures are
> illustrative, not statistically representative.

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
| **Custo por chamada** | ~$0.0001/req em Haiku. Prompt caching reduz, mas não zera. Sem rate limiting no MVP. |
| **Sem reask em fail** | Bloqueio direto reduz UX (sem auto-correção). Reask é Extras. |
| **Reasoning pode vazar PII** | Reasoning truncado em 200 chars reduz blast radius, mas observabilidade tem limitação aceita no MVP. |

### Roadmap (Extras)

- Annotator independente para validação cruzada das fixtures
- Paraphrasing dataset (variações do Beat 4 e demais violações)
- Histórico de conversa (janela deslizante de N turnos)
- Calibração contra labels humanos (Cohen's kappa, ~100 casos)
- Reask 1x com auto-correção do output
