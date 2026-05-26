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
