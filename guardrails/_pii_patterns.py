"""
Shared PII regex patterns for PT-BR.

Single source of truth used by PIIValidator and the logger sanitizer.
Keeping patterns in one place avoids duplication drift (security risk).
"""

from __future__ import annotations

import re

PII_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "telefone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    "cpf": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "cartao": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
}

COMPILED_PII: dict[str, re.Pattern] = {
    k: re.compile(v) for k, v in PII_PATTERNS.items()
}
