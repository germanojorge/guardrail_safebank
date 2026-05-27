"""
PIIValidator — detects PII in PT-BR text using regex patterns.

`details` keys populated by `run()`:
- `entities`: dict mapping entity type to list of (start, end) span tuples; omits types with zero matches
- `stage`: echoes the constructor `stage` param ("input" or "output")
- `patterns_checked`: list of all pattern names checked (always all 4)
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from guardrails._pii_patterns import COMPILED_PII, PII_PATTERNS
from guardrails.validators.base import ValidatorResult


class PIIValidator:
    name = "pii"

    def __init__(self, stage: str = "input") -> None:
        if stage not in {"input", "output"}:
            raise ValueError(f"stage must be 'input' or 'output', got {stage!r}")
        self.stage = stage

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()
        entities: dict[str, list[tuple[int, int]]] = {}
        for entity_type, pattern in COMPILED_PII.items():
            spans = [m.span() for m in pattern.finditer(text)]
            if spans:
                entities[entity_type] = spans
        passed = not entities
        first_entity = next(iter(entities), None) if entities else None
        return ValidatorResult(
            passed=passed,
            category=f"pii_{self.stage}",
            score=None,
            details={
                "rule_violated": first_entity,
                "entities": entities,
                "stage": self.stage,
                "patterns_checked": list(PII_PATTERNS.keys()),
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
