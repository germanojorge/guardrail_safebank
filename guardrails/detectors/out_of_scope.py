"""Detector de perguntas fora do escopo bancário (R5 da rubrica).

Versão keyword-only: verifica se o texto contém ao menos um termo da allowlist
bancária PT-BR. Limitação declarada em LIMITATIONS.md — sem embedding similarity.
"""

from __future__ import annotations

import re

from guardrails.detectors.base import DetectionResult

# ~40 termos bancários PT-BR que indicam escopo válido
_BANKING_TERMS = [
    "pix",
    "ted",
    "doc",
    "transferência",
    "transferencia",
    "conta",
    "saldo",
    "extrato",
    "fatura",
    "boleto",
    "cartão",
    "cartao",
    "débito",
    "debito",
    "crédito",
    "credito",
    "empréstimo",
    "emprestimo",
    "financiamento",
    "parcela",
    "prestação",
    "prestacao",
    "investimento",
    "aplicação",
    "aplicacao",
    "resgate",
    "rendimento",
    "cdb",
    "lci",
    "lca",
    "tesouro",
    "fundos",
    "banco",
    "agência",
    "agencia",
    "conta-corrente",
    "poupança",
    "poupanca",
    "tarifa",
    "anuidade",
    "limite",
    "cheque especial",
    "seguro",
    "previdência",
    "previdencia",
    "consórcio",
    "consorcio",
    "cpf",
    "cnpj",
    "senha",
    "token",
    "autenticação",
    "autenticacao",
    "saque",
    "depósito",
    "deposito",
    "recarga",
]

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _BANKING_TERMS) + r")\b",
    re.IGNORECASE | re.UNICODE,
)


class OutOfScopeDetector:
    """Retorna detected=True quando o texto está FORA do escopo bancário."""

    def detect(self, text: str) -> DetectionResult:
        m = _PATTERN.search(text)
        if m:
            # Encontrou termo bancário → dentro do escopo → NÃO é out-of-scope
            return DetectionResult(detected=False)
        return DetectionResult(
            detected=True,
            rule_id="no_banking_term",
            confidence=0.7,
            matched_patterns=[],
        )
