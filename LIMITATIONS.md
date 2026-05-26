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
| **No CNPJ** | CNPJ numbers are not detected. |
| **No conta bancária** | Bank account numbers (agência + conta) are not detected. |
| **No NER (names, addresses)** | Person names, street addresses, and city/state are not detected. Presidio Analyzer with PT-BR NER models is the planned Extras path (see CLAUDE.md). |
| **Phone regex misses 11-digit mobile** | Pattern `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` matches exactly 10-digit sequences (e.g., `011-912-3456`). Brazilian mobile numbers with DDD are 11 digits when unformatted (e.g., `11912345678`) — these are missed. Formats `(11) 91234-5678` and `+55 11 91234-5678` are also missed. |
| **Phone false positives** | The phone regex can match 10-digit suffixes of CPF numbers or numeric dates embedded in text. Since patterns are checked independently, a CPF match also triggers a `cpf` block in the same call — no functional problem, but worth knowing. |
| **Email regex is RFC-naive** | Under-matches unicode TLDs (e.g., `.рф`, `.中文`). May over-match inside code blocks or markdown URLs where the surrounding word boundary does not apply. |
| **Card regex over-matches** | Any 16-digit sequence in groups of 4 (loyalty IDs, tracking codes, serial numbers) will trigger a block. Future Luhn validation would reduce false positives. |

### Layered-defense comparison (jailbreak — added when jailbreak validator lands)

| Layer | Bypass rate on JailbreakBench (paraphrase set) |
|-------|----------------------------------------------|
| Substring fast-path only | TBD — populated after SCRUM-4 implementation |
| Substring + DeBERTa | TBD — populated after SCRUM-4 implementation |

### Fixture closed-loop caveat

The PII test fixtures (`tests/fixtures/pii_samples.py`) were hand-crafted by the same agent that wrote the regex patterns. They demonstrate **pattern coverage** (each of the 4 entity types is exercised), not **adversarial breadth**. No external PT-BR PII corpus was available at MVP scope. Per `building-rigorously.md §1`, these tests validate internal consistency, not correctness against real-world data distributions.

### Roadmap (Extras)

Per CLAUDE.md Extras table:
- **Presidio Analyzer** with PT-BR NER models — adds name/address detection
- **CPF checksum** (Módulo 11 algorithm) — eliminates valid-format/invalid-number false positives
- **CNPJ with checksum**
- **Luhn algorithm for cards** — reduces 16-digit sequence false positives
- **PII masking** instead of hard block — better UX, same security guarantee
