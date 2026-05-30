"""Detector de tentativas fraudulentas / ações não-executáveis (R3 da rubrica)."""

from __future__ import annotations

import re

from guardrails.detectors.base import DetectionResult

_RULES: list[tuple[str, str]] = [
    (
        "credenciais",
        r"(me\s+diga|informe|compartilhe|envie|me\s+passe)"
        r".{0,30}(senha|token|pin|código\s+de\s+segurança|cvv|dados\s+de\s+acesso)"
        r"|(sua\s+senha|seu\s+token|seu\s+pin)\s+(é|foi|ficou|deve\s+ser)"
        r"|senha\s+padrão\s+(é|foi|costuma\s+ser)",
    ),
    (
        "personificacao",
        r"(sou|somos)\s+(do\s+)?(suporte|atendimento|setor|departamento|equipe)"
        r".{0,30}(banco|itaú|bradesco|caixa|santander|nubank|inter)"
        r"|funcionário.{0,20}(banco|instituição\s+financeira)"
        r"|(técnico|analista|gerente)\s+do\s+banco"
        r"|estou\s+ligando\s+(do|pelo|em\s+nome\s+do)\s+banco",
    ),
    (
        "doc_falso",
        r"(documento|comprovante|extrato|declaração|laudo).{0,20}"
        r"(falso|fraudado|falsificado|adulterado|forjado)"
        r"|criei?\s+(um\s+)?(documento|comprovante|extrato).{0,20}(para\s+você|bancário)"
        r"|como\s+(criar?|falsificar?|adulterar?).{0,20}(documento|comprovante|extrato)",
    ),
    (
        "bypass_auth",
        r"(ignore|pule|burle|contorne|evite)"
        r".{0,30}(autenticação|verificação|validação|2fa|dois\s+fatores|mfa|captcha)"
        r"|como\s+(passar|burlar)\s+(pela\s+)?(segurança|autenticação|verificação)"
        r"|sem\s+(autenticação|verificação|validação|login)",
    ),
]

_COMPILED: list[tuple[str, re.Pattern[str]]] = [(rule_id, re.compile(pattern, re.IGNORECASE | re.UNICODE)) for rule_id, pattern in _RULES]


class FraudDetector:
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
