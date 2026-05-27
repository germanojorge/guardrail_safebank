"""
PIIValidator — detects PII in PT-BR text using two complementary layers:

Layer 1 — Regex + checksum (fast, deterministic)
    CPF (formatted + raw, Módulo 11), CNPJ (checksum), cartão (Luhn),
    telefone (PT-BR DDD formats), email.

Layer 2 — Presidio + spaCy pt_core_news_sm (NER, ~50ms extra)
    PERSON (person names), LOCATION (addresses, cities).
    Only runs when Layer 1 passes to avoid wasted latency on already-blocked inputs.
    Gracefully disabled if presidio-analyzer or the spaCy model is not installed.

`details` keys populated by `run()`:
- `entities`: dict mapping entity type → list of (start, end) span tuples
- `stage`: "input" or "output"
- `patterns_checked`: regex pattern names checked
- `presidio_enabled`: bool — whether Presidio layer was active
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from guardrails._pii_patterns import CHECKSUM_VALIDATORS, COMPILED_PII, PII_PATTERNS
from guardrails.validators.base import ValidatorResult

# cpf_raw is an implementation detail; surface it as "cpf" to callers
_ALIAS: dict[str, str] = {"cpf_raw": "cpf"}

# Presidio entity types we care about (NER-only — everything else is handled by regex)
_PRESIDIO_ENTITIES = ["PERSON", "LOCATION"]
_PRESIDIO_LANG = "pt"

logger = logging.getLogger(__name__)


def _build_presidio_engine():
    """Build a Presidio AnalyzerEngine configured for PT-BR with spaCy.

    Returns None (with a warning) if presidio-analyzer or pt_core_news_sm is missing.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError:
        logger.warning("presidio-analyzer not installed — NER-based PII detection (PERSON, LOCATION) disabled")
        return None

    try:
        config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": _PRESIDIO_LANG, "model_name": "pt_core_news_sm"}],
        }
        provider = NlpEngineProvider(nlp_configuration=config)
        engine = AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            supported_languages=[_PRESIDIO_LANG],
        )
        return engine
    except OSError:
        logger.warning("spaCy model 'pt_core_news_sm' not found — run: python -m spacy download pt_core_news_sm. NER-based PII detection (PERSON, LOCATION) disabled.")
        return None


class PIIValidator:
    name = "pii"

    def __init__(self, stage: str = "input", presidio_engine=None) -> None:
        """
        Args:
            stage: "input" or "output".
            presidio_engine: pre-built AnalyzerEngine instance (shared across
                validators to avoid loading the spaCy model twice). Pass None to
                build a new engine; pass False to disable Presidio entirely.
        """
        if stage not in {"input", "output"}:
            raise ValueError(f"stage must be 'input' or 'output', got {stage!r}")
        self.stage = stage

        if presidio_engine is False:
            self._presidio = None
        elif presidio_engine is None:
            self._presidio = _build_presidio_engine()
        else:
            self._presidio = presidio_engine

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()
        entities: dict[str, list[tuple[int, int]]] = {}

        # ── Layer 1: regex + checksum ─────────────────────────────────────
        for entity_type, pattern in COMPILED_PII.items():
            raw_spans = [m.span() for m in pattern.finditer(text)]
            if not raw_spans:
                continue

            checksum = CHECKSUM_VALIDATORS.get(entity_type)
            valid_spans = [s for s in raw_spans if checksum(text[s[0] : s[1]])] if checksum else raw_spans
            if not valid_spans:
                continue

            canonical = _ALIAS.get(entity_type, entity_type)
            entities.setdefault(canonical, []).extend(valid_spans)

        # ── Layer 2: Presidio NER (PERSON, LOCATION) ──────────────────────
        if self._presidio and not entities:
            # Only run if Layer 1 found nothing — avoids latency on already-blocked inputs
            try:
                results = self._presidio.analyze(
                    text=text,
                    entities=_PRESIDIO_ENTITIES,
                    language=_PRESIDIO_LANG,
                )
                for r in results:
                    entities.setdefault(r.entity_type.lower(), []).append((r.start, r.end))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Presidio analysis failed: %s", exc)

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
                "presidio_enabled": self._presidio is not None,
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
