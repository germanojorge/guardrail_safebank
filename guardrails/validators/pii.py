"""
PIIValidator — detects PII in PT-BR text using regex patterns.

`details` keys populated by `run()`:
- `entities`: dict mapping entity type to list of (start, end) span tuples; omits types with zero matches
- `stage`: echoes the constructor `stage` param ("input" or "output")
- `patterns_checked`: list of all pattern names checked (always all 4)
"""

from __future__ import annotations

import re
import time
from typing import Any, Mapping

from .base import ValidatorResult

PII_PATTERNS: dict[str, str] = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "telefone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    "cpf": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "cartao": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
}


class PIIValidator:
    name = "pii"

    def __init__(self, stage: str = "input") -> None:
        if stage not in {"input", "output"}:
            raise ValueError(f"stage must be 'input' or 'output', got {stage!r}")
        self.stage = stage
        self._compiled = {k: re.compile(v) for k, v in PII_PATTERNS.items()}

    def run(
        self, text: str, context: Mapping[str, Any] | None = None
    ) -> ValidatorResult:
        t0 = time.perf_counter()
        entities: dict[str, list[tuple[int, int]]] = {}
        for entity_type, pattern in self._compiled.items():
            spans = [m.span() for m in pattern.finditer(text)]
            if spans:
                entities[entity_type] = spans
        passed = not entities
        return ValidatorResult(
            passed=passed,
            category=f"pii_{self.stage}",
            score=None,
            details={
                "entities": entities,
                "stage": self.stage,
                "patterns_checked": list(PII_PATTERNS.keys()),
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
