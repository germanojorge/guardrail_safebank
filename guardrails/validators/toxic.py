"""
ToxicValidator — detects toxic content using Detoxify.

`details` keys populated by `run()`:
- `subscores`: dict mapping each of the 5 sub-categories to their float score
- `top_category`: the sub-category with the highest score
- `threshold`: the threshold used for this call
- `model`: the model name used (e.g. "multilingual")
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from detoxify import Detoxify

from .base import ValidatorResult


class ToxicValidator:
    name = "toxicity"

    _CATEGORIES = ("toxicity", "severe_toxicity", "obscene", "threat", "insult")

    def __init__(
        self,
        threshold: float = 0.7,
        model_name: str = "multilingual",
        model: Detoxify | None = None,
    ) -> None:
        self.threshold = threshold
        self._model_name = model_name
        self._model = model if model is not None else Detoxify(model_name)

    def run(
        self, text: str, context: Mapping[str, Any] | None = None
    ) -> ValidatorResult:
        t0 = time.perf_counter()
        scores = self._model.predict(text)
        subscores = {k: float(scores[k]) for k in self._CATEGORIES}
        top_category, top_score = max(subscores.items(), key=lambda kv: kv[1])
        passed = top_score < self.threshold
        return ValidatorResult(
            passed=passed,
            category="toxicity",
            score=top_score,
            details={
                "subscores": subscores,
                "top_category": top_category,
                "threshold": self.threshold,
                "model": self._model_name,
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
