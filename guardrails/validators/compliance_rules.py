"""RuleBasedComplianceValidator — compliance bancário sem LLM.

Substitui ComplianceValidator quando LLM_PROVIDER=mock.
Mantém a mesma interface pública: run(text) -> ValidatorResult com os
mesmos campos em `details` (verdict, rule_violated, reasoning, model).

Mapeamento detector → rubrica:
  financial_advice.promessa_rentabilidade / minimizacao_risco → R1
  financial_advice.recomendacao_direta / alocacao_indevida
                  / comparacao_absoluta / urgencia            → R2
  fraud.*                                                     → R3
  data_leak.*                                                 → R4
  out_of_scope.no_banking_term                               → R5

LIMITAÇÕES (declaradas em LIMITATIONS.md):
- Falha em paráfrase e negação implícita (ex: "não é sem risco" ≠ promessa)
- out_of_scope é keyword-only: sem embedding similarity → mais falsos positivos
- Sem detecção de promessa via tom (só via léxico)
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from guardrails.detectors.data_leak import DataLeakDetector
from guardrails.detectors.financial_advice import FinancialAdviceDetector
from guardrails.detectors.fraud import FraudDetector
from guardrails.detectors.out_of_scope import OutOfScopeDetector
from guardrails.validators.base import ValidatorResult

_FINANCIAL_R1 = {"promessa_rentabilidade", "minimizacao_risco"}
_FINANCIAL_R2 = {"recomendacao_direta", "alocacao_indevida", "comparacao_absoluta", "urgencia"}


def _map_rule(detector_name: str, rule_id: str | None) -> str:
    if detector_name == "financial_advice":
        if rule_id in _FINANCIAL_R1:
            return "R1"
        return "R2"
    if detector_name == "fraud":
        return "R3"
    if detector_name == "data_leak":
        return "R4"
    if detector_name == "out_of_scope":
        return "R5"
    return "R5"


class RuleBasedComplianceValidator:
    name = "compliance"

    def __init__(self) -> None:
        self._financial = FinancialAdviceDetector()
        self._fraud = FraudDetector()
        self._data_leak = DataLeakDetector()
        self._out_of_scope = OutOfScopeDetector()

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()

        if not text.strip():
            return ValidatorResult(
                passed=True,
                category="compliance",
                score=None,
                details={
                    "verdict": "pass",
                    "rule_violated": None,
                    "reasoning": "",
                    "model": "rule_based",
                    "stop_reason": None,
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        checks = [
            ("financial_advice", self._financial.detect(text)),
            ("fraud", self._fraud.detect(text)),
            ("data_leak", self._data_leak.detect(text)),
            ("out_of_scope", self._out_of_scope.detect(text)),
        ]

        for detector_name, result in checks:
            if result.detected:
                rule = _map_rule(detector_name, result.rule_id)
                reasoning = f"[rule_based/{detector_name}/{result.rule_id}] " + (", ".join(result.matched_patterns) if result.matched_patterns else "pattern match")
                return ValidatorResult(
                    passed=False,
                    category="compliance",
                    score=result.confidence,
                    details={
                        "verdict": "fail",
                        "rule_violated": rule,
                        "reasoning": reasoning[:200],
                        "model": "rule_based",
                        "stop_reason": None,
                    },
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )

        return ValidatorResult(
            passed=True,
            category="compliance",
            score=None,
            details={
                "verdict": "pass",
                "rule_violated": None,
                "reasoning": "",
                "model": "rule_based",
                "stop_reason": None,
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
