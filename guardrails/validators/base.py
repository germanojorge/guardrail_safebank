"""
Validator Protocol and ValidatorResult for the guardrails pipeline.

Notes:
- `score` is NOT comparable across validators (toxicity max-sub-score vs. classifier
  confidence vs. None for rule-based validators). Do not aggregate scores cross-validator.
- `details` keys are validator-specific; each concrete class documents its own keys.
- `runtime_checkable` only verifies attribute presence, not method signatures.
  For strict structural checking, run `mypy guardrails/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass
class ValidatorResult:
    passed: bool
    category: str
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None


@runtime_checkable
class Validator(Protocol):
    name: str

    def run(
        self, text: str, context: Mapping[str, Any] | None = None
    ) -> ValidatorResult: ...
