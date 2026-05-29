"""Detector de aconselhamento financeiro indevido (R1 e R2 da rubrica)."""

from __future__ import annotations

import re

from guardrails.detectors.base import DetectionResult

_RULES: list[tuple[str, str, list[str]]] = [
    (
        "promessa_rentabilidade",
        r"(rendimento|retorno|lucro|ganho).{0,30}(garanti|certo|assegurad|certeza)"
        r"|garanti.{0,20}(rendimento|retorno|lucro|ganho)"
        r"|rentabilidade.{0,20}(garanti|certa|fixa)"
        r"|\d+\s*%\s*(ao\s*(mês|ano|dia)|a\.a\.|a\.m\.)\s*(garanti|certo|assegurad)"
        r"|(sem\s+risco|risco\s+zero|livre\s+de\s+risco).{0,30}(rendimento|retorno|ganho)",
        [],
    ),
    (
        "minimizacao_risco",
        r"(sem\s+risco|risco\s+zero|risco\s+nulo|totalmente\s+seguro|100\s*%\s*seguro"
        r"|não\s+(tem|há)\s+(como\s+perder|risco)|impossível\s+perder"
        r"|nunca\s+(vai\s+perder|perde))",
        [],
    ),
    (
        "recomendacao_direta",
        r"(você\s+dev(e|eria)|te\s+recomendo|recomendo\s+que|eu\s+indicaria?|minha\s+sugestão\s+é)"
        r".{0,40}(investir?|comprar?|aplicar?|colocar?|adquirir?)"
        r"|(invista|aplique|compre|adquira)\s+(agora|hoje|imediatamente|neste\s+momento)"
        r"|invista\s+(em|no|na)\s+\w",
        [],
    ),
    (
        "alocacao_indevida",
        r"(coloque|ponha|transfira|mova).{0,20}(tudo|todo\s+o\s+dinheiro|toda\s+a\s+reserva|100\s*%)"
        r".{0,20}(em|no|na|para)"
        r"|concentre.{0,20}(recursos|capital|dinheiro|patrimônio)"
        r"|aposte\s+(tudo|alto|forte)\s+(em|no|na)",
        [],
    ),
    (
        "comparacao_absoluta",
        r"(melhor|único|exclusivo|superior\s+a\s+todos)"
        r".{0,30}(investimento|aplicação|produto\s+financeiro|opção)"
        r"|(nenhum\s+outro|nada\s+melhor\s+que|incomparável).{0,30}(rendimento|retorno|ganho)",
        [],
    ),
    (
        "urgencia",
        r"(só\s+hoje|apenas\s+hoje|somente\s+hoje"
        r"|por\s+tempo\s+limitado|oferta\s+por\s+tempo"
        r"|última\s+chance|corra\s+(e\s+)?(invista|aplique|garanta)"
        r"|antes\s+que\s+(acabe|termine|encerre)"
        r"|não\s+perca\s+essa\s+(oportunidade|chance))",
        [],
    ),
]

_COMPILED: list[tuple[str, re.Pattern[str]]] = [(rule_id, re.compile(pattern, re.IGNORECASE | re.UNICODE)) for rule_id, pattern, _ in _RULES]


class FinancialAdviceDetector:
    def detect(self, text: str) -> DetectionResult:
        for rule_id, pattern in _COMPILED:
            m = pattern.search(text)
            if m:
                return DetectionResult(
                    detected=True,
                    rule_id=rule_id,
                    confidence=1.0,
                    matched_patterns=[m.group(0)],
                )
        return DetectionResult(detected=False)
