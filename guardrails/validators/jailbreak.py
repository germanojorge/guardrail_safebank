"""
JailbreakValidator — two-layer prompt injection detector.

Layer 1: substring fast-path against a curated keyword list (<5ms).
Layer 2: DeBERTa classifier (`protectai/deberta-v3-base-prompt-injection-v2`) for
paraphrased attacks that bypass Layer 1 (<300ms CPU).

`details` keys populated by `run()`:
- `layer_caught`: "substring" | "deberta" | None (benign)
- `substring_match_count`: int — number of keyword hits in Layer 1
- `deberta_score`: float | None — classifier score (None if substring caught first)
- `threshold`: float — DeBERTa threshold used
- `substring_keywords_checked`: int — size of the keyword list
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from .base import ValidatorResult


class JailbreakValidator:
    name = "jailbreak"

    _JAILBREAK_KEYWORDS: tuple[str, ...] = (
        # Portuguese
        "esqueça todas as instruções",
        "ignore as instruções anteriores",
        "ignore suas instruções",
        "finja que você é",
        "você não tem restrições",
        "modo desenvolvedor",
        "dan ",
        " dan",
        "ignore os limites",
        "sem restrições",
        # English (common in JailbreakBench)
        "ignore previous instructions",
        "forget your instructions",
        "you are now",
        "do anything now",
        "pretend you are",
        "act as if",
        "disregard all",
        "override",
        "ignore all previous",
    )

    def __init__(
        self,
        threshold: float = 0.85,
        pipeline=None,
    ) -> None:
        self.threshold = threshold
        self._pipeline = pipeline if pipeline is not None else self._load_pipeline()

    @staticmethod
    def _load_pipeline():
        from transformers import pipeline

        return pipeline(
            "text-classification",
            model="protectai/deberta-v3-base-prompt-injection-v2",
            device=-1,  # CPU
        )

    def run(
        self, text: str, context: Mapping[str, Any] | None = None
    ) -> ValidatorResult:
        t0 = time.perf_counter()

        if not text.strip():
            return ValidatorResult(
                passed=True,
                category="jailbreak",
                score=None,
                details={
                    "layer_caught": None,
                    "substring_match_count": 0,
                    "deberta_score": None,
                    "threshold": self.threshold,
                    "substring_keywords_checked": len(self._JAILBREAK_KEYWORDS),
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # Layer 1 — substring fast-path
        lowered = text.lower()
        match_count = sum(1 for kw in self._JAILBREAK_KEYWORDS if kw in lowered)
        if match_count > 0:
            return ValidatorResult(
                passed=False,
                category="jailbreak",
                score=1.0,
                details={
                    "layer_caught": "substring",
                    "substring_match_count": match_count,
                    "deberta_score": None,
                    "threshold": self.threshold,
                    "substring_keywords_checked": len(self._JAILBREAK_KEYWORDS),
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # Layer 2 — DeBERTa classifier
        result = self._pipeline(text)[0]
        label: str = result["label"]
        score: float = result["score"]

        if label == "INJECTION" and score >= self.threshold:
            return ValidatorResult(
                passed=False,
                category="jailbreak",
                score=score,
                details={
                    "layer_caught": "deberta",
                    "substring_match_count": 0,
                    "deberta_score": score,
                    "threshold": self.threshold,
                    "substring_keywords_checked": len(self._JAILBREAK_KEYWORDS),
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # Benign
        return ValidatorResult(
            passed=True,
            category="jailbreak",
            score=None,
            details={
                "layer_caught": None,
                "substring_match_count": 0,
                "deberta_score": score,
                "threshold": self.threshold,
                "substring_keywords_checked": len(self._JAILBREAK_KEYWORDS),
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
