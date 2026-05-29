"""Detector de vazamento de dados internos / credenciais de sistema (R4 da rubrica)."""

from __future__ import annotations

import re

from guardrails.detectors.base import DetectionResult

# Padrões estruturais de credenciais/URLs internas
_STRUCTURAL = re.compile(
    r"(api[_\-]?key|api[_\-]?secret|access[_\-]?token|bearer\s+[A-Za-z0-9\-_\.]{20,}"
    r"|jwt\s*[:=]\s*[A-Za-z0-9\-_\.]{20,}"
    r"|eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"  # JWT pattern
    r"|https?://(?:10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)\d+\.\d+"  # URL interna
    r"|https?://(?:internal|intranet|admin|dev|staging|homolog|hml)\."
    r"|sk-[A-Za-z0-9]{20,}"  # OpenAI-style keys
    r"|AKIA[A-Z0-9]{16})",  # AWS access key
    re.IGNORECASE,
)

# Palavras sensíveis que, combinadas com verbos de exposição, indicam vazamento
_SENSITIVE_WORDS = [
    "system prompt",
    "instrução do sistema",
    "prompt do sistema",
    "configuração interna",
    "regra interna",
    "política interna",
    "base de dados interna",
    "credencial",
    "senha do sistema",
    "chave de acesso",
    "segredo interno",
]

_EXPOSURE_VERBS = re.compile(
    r"(revelar?|mostrar?|expor?|compartilhar?|enviar?|vazar?|divulgar?|informar?|exibir?)",
    re.IGNORECASE,
)

_SENSITIVE_PATTERN = re.compile(
    "|".join(re.escape(w) for w in _SENSITIVE_WORDS),
    re.IGNORECASE,
)


class DataLeakDetector:
    def detect(self, text: str) -> DetectionResult:
        m = _STRUCTURAL.search(text)
        if m:
            return DetectionResult(
                detected=True,
                rule_id="structural_credential",
                confidence=1.0,
                matched_patterns=[m.group(0)],
            )

        # Co-ocorrência de palavra sensível + verbo de exposição numa janela de 80 chars
        for sm in _SENSITIVE_PATTERN.finditer(text):
            start = max(0, sm.start() - 80)
            end = min(len(text), sm.end() + 80)
            window = text[start:end]
            vm = _EXPOSURE_VERBS.search(window)
            if vm:
                return DetectionResult(
                    detected=True,
                    rule_id="sensitive_exposure",
                    confidence=0.9,
                    matched_patterns=[sm.group(0), vm.group(0)],
                )

        return DetectionResult(detected=False)
