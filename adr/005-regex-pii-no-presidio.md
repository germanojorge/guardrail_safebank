# ADR-005: Regex-Only PII (No Presidio)

## Status

Accepted (2026-05-25)

## Context

Presidio Analyzer with PT-BR NER models would add ~2–3 hours to the 2-day MVP budget. Bidirectional PII blocking (input and output) is mandatory because the chatbot must not leak customer PII in its responses, and the user must not send PII through the chat interface.

## Decision

Use four regex patterns in a shared `_pii_patterns.py` module: `email`, `telefone`, `cpf` (formatted `XXX.XXX.XXX-XX`), and `cartao` (16 digits in groups of 4). Apply the same patterns to both input and output text. Detection triggers a direct block; masking is deferred to Extras.

## Consequences

**Positive:**
- <1ms latency, zero additional dependencies.
- Deterministic and fully auditable.
- Works offline.

**Negative:**
- No checksum validation (CPF without Módulo 11, card without Luhn).
- No NER for names, addresses, or unformatted CPF (`12345678909`).
- No CNPJ or bank account detection.
- Card regex over-matches: any 16-digit grouped sequence (loyalty IDs, tracking codes) triggers a block.

**Neutral:**
- Presidio integration remains a planned Extras item; the adapter pattern makes swapping straightforward.
