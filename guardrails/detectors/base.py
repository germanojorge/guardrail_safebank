from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DetectionResult:
    detected: bool
    rule_id: str | None = None
    confidence: float = 0.0
    matched_patterns: list[str] = field(default_factory=list)
