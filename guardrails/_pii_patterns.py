"""
Shared PII regex patterns for PT-BR.

Single source of truth used by PIIValidator and the logger sanitizer.
Keeping patterns in one place avoids duplication drift (security risk).

Checksum validators
-------------------
CHECKSUM_VALIDATORS maps entity types to a function ``(raw_str) -> bool``.
After a regex span is found, the validator is called with the raw matched text.
Spans that fail the checksum are silently dropped — they matched the regex format
but are not mathematically valid (e.g. a random 11-digit sequence that happens to
look like a CPF but has wrong check digits).

Entities without a checksum entry (email, telefone) are always trusted on regex match.
"""

from __future__ import annotations

import re
from typing import Callable


# ── Regex patterns ────────────────────────────────────────────────────────────

PII_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    # PT-BR phone — two sub-patterns joined with |:
    #   1. Formatted: (11) 91234-5678 | 11 91234-5678 | +55 11 91234-5678
    #      Requires explicit separator (space or dash) after DDD to avoid matching
    #      substrings of CPF or card numbers.
    #   2. Unformatted mobile: 11912345678 — exactly DDD(2) + 9 + 8 digits (celular
    #      PT-BR always starts with 9). The (?<!\d)/(?!\d) guards prevent matching
    #      inside longer digit sequences (e.g. a CPF where digit[2]≠9).
    # PT-BR phone — two sub-patterns joined with |:
    #   1. Formatted: (11) 91234-5678 | 11 91234-5678 | +55 11 91234-5678 | 011-912-3456
    #      (?<!\d) ensures DDD is not embedded inside a longer digit sequence
    #      (prevents matching substrings of CPF, card, or loyalty codes).
    #      0? allows optional leading zero before DDD (e.g. 011 for São Paulo).
    #      The prefix after DDD is 3–5 digits to cover both old 4-digit local
    #      numbers and newer 5-digit mobile prefixes.
    #   2. Unformatted mobile: 11912345678 — DDD(2) + 9 + 8 digits; the leading
    #      9 distinguishes celular from fixed lines and prevents matching CPF
    #      sequences where digit[2] is never 9 for common test CPFs.
    "telefone": (
        r"(?<!\d)(?:\+55[\s\-]?)?(?:\(\d{2}\)[\s\-]?|0?\d{2}[\s\-])\d{3,5}[\s\-]?\d{4}(?!\d)"
        r"|(?<!\d)\d{2}9\d{8}(?!\d)"
    ),
    # CPF formatted: 000.000.000-00
    "cpf": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    # CPF unformatted: 00000000000 (11 plain digits, checksum filters out non-CPFs)
    "cpf_raw": r"(?<!\d)\d{11}(?!\d)",
    # CNPJ formatted: 00.000.000/0000-00
    "cnpj": r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    # Card: 16 digits in groups of 4 (Luhn filters out non-card sequences)
    "cartao": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
}

COMPILED_PII: dict[str, re.Pattern] = {k: re.compile(v) for k, v in PII_PATTERNS.items()}


# ── Checksum validators ───────────────────────────────────────────────────────


def _validate_cpf(raw: str) -> bool:
    """Return True if raw string is a mathematically valid CPF (Módulo 11)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 11:
        return False
    if len(set(digits)) == 1:  # 000...0, 111...1, etc.
        return False
    # First check digit
    total = sum(int(d) * (10 - i) for i, d in enumerate(digits[:9]))
    r = total % 11
    check1 = 0 if r < 2 else 11 - r
    if int(digits[9]) != check1:
        return False
    # Second check digit
    total = sum(int(d) * (11 - i) for i, d in enumerate(digits[:10]))
    r = total % 11
    check2 = 0 if r < 2 else 11 - r
    return int(digits[10]) == check2


def _validate_cnpj(raw: str) -> bool:
    """Return True if raw string is a mathematically valid CNPJ."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 14:
        return False
    if len(set(digits)) == 1:
        return False
    # First check digit
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:12], weights1))
    r = total % 11
    check1 = 0 if r < 2 else 11 - r
    if int(digits[12]) != check1:
        return False
    # Second check digit
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:13], weights2))
    r = total % 11
    check2 = 0 if r < 2 else 11 - r
    return int(digits[13]) == check2


def _validate_luhn(raw: str) -> bool:
    """Return True if raw string passes the Luhn algorithm (credit/debit cards)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 16:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# Map entity type → validator. Entities absent here are always trusted on regex match.
CHECKSUM_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "cpf": _validate_cpf,
    "cpf_raw": _validate_cpf,
    "cnpj": _validate_cnpj,
    "cartao": _validate_luhn,
}
