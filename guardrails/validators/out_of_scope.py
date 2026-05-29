"""
OutOfScopeValidator — blocks non-banking queries using seed-based cosine similarity.

Uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` to embed
input text and compare against pre-defined in-scope (banking) and out-of-scope
(generic non-banking) seed texts via cosine similarity.

Blocking logic:
  1. max_sim_in = max(sim(input, seed) for seed in in_scope)
  2. max_sim_out = max(sim(input, seed) for seed in out_of_scope)
  3. Block if:
     a. max_sim_in < threshold_in AND max_sim_out > threshold_out
     b. max_sim_out > max_sim_in + margin

`details` keys populated by `run()`:
- `closest_in_scope`: str | None — closest in-scope seed text
- `closest_out_of_scope`: str | None — closest out-of-scope seed text
- `scores`: dict — {"max_in": float, "max_out": float}
- `threshold_in`: float
- `threshold_out`: float
- `margin`: float
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping

import numpy as np

from .base import ValidatorResult

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_DEFAULT_IN_SCOPE: list[str] = [
    "Como faço um Pix?",
    "Qual é o saldo da minha conta corrente?",
    "Quero abrir uma conta poupança.",
    "Quais são as tarifas do cartão de crédito?",
    "Como faço para aumentar o limite do cartão?",
    "Qual o horário de funcionamento da agência?",
    "Preciso de segunda via do boleto.",
    "Como consulto o extrato bancário?",
    "Quero fazer uma transferência TED.",
    "Como funciona o consórcio?",
    "Qual a taxa de juros do empréstimo pessoal?",
    "Como contratar um seguro de vida?",
    "Quero investir em um CDB.",
    "Como resgatar uma aplicação?",
    "Qual o rendimento da poupança?",
    "Como cadastrar uma chave Pix?",
    "Preciso alterar meu endereço de cobrança.",
    "Como faço para pagar um boleto vencido?",
    "Quero cancelar o débito automático.",
    "Como solicitar um cartão adicional?",
    "Qual o valor mínimo para abrir uma conta?",
    "Como faço portabilidade de salário?",
    "Quero simular um financiamento imobiliário.",
    "Como consulto meus investimentos?",
    "Preciso de um extrato para declaração de imposto de renda.",
    "Como bloquear o cartão temporariamente?",
    "Qual o prazo para o dinheiro cair na conta?",
    "Como ativar notificações de transação?",
    "Quero saber sobre capitalização.",
    "Como funciona o cheque especial?",
]

_DEFAULT_OUT_OF_SCOPE: list[str] = [
    "Como fazer bolo de chocolate?",
    "Qual a capital da Austrália?",
    "Me ensina a programar em Python.",
    "Quem ganhou a Copa do Mundo de 2018?",
    "Como consertar uma torneira pingando?",
    "Qual o melhor celular para comprar em 2024?",
    "Me conte uma piada.",
    "Como fazer exercícios de musculação?",
    "Qual a fórmula química da água?",
    "Escreva um poema sobre o mar.",
    "Como trocar o pneu do carro?",
    "Quais são os sintomas da dengue?",
    "Como plantar tomate em casa?",
    "Quem foi Machado de Assis?",
    "Como fazer uma redação nota 1000 no ENEM?",
    "Me recomende um filme de terror.",
    "Qual a distância entre São Paulo e Rio de Janeiro?",
    "Como criar um canal no YouTube?",
    "O que é computação quântica?",
    "Como fazer pão caseiro?",
]

FALLBACK_MESSAGE = "Só posso ajudar com assuntos bancários. Para outras dúvidas, entre em contato com um gerente ou visite uma agência."


class OutOfScopeValidator:
    name = "out_of_scope"

    def __init__(
        self,
        threshold_in: float = 0.40,
        threshold_out: float = 0.50,
        margin: float = 0.15,
        embedding_model=None,
        in_scope_seeds: list[str] | None = None,
        out_of_scope_seeds: list[str] | None = None,
        seeds_path: str = "data/out_of_scope_seeds.json",
    ) -> None:
        self.threshold_in = threshold_in
        self.threshold_out = threshold_out
        self.margin = margin

        if embedding_model is not None:
            self._model = embedding_model
        else:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(_MODEL_NAME)

        seeds = self._load_seeds(seeds_path, in_scope_seeds, out_of_scope_seeds)
        self._in_scope_seeds = seeds["in_scope"]
        self._out_of_scope_seeds = seeds["out_of_scope"]

        self._in_embeddings = self._embed_all(self._in_scope_seeds)
        self._out_embeddings = self._embed_all(self._out_of_scope_seeds)

    @staticmethod
    def _load_seeds(
        path: str,
        in_scope_seeds: list[str] | None,
        out_of_scope_seeds: list[str] | None,
    ) -> dict[str, list[str]]:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "in_scope": data.get("in_scope", _DEFAULT_IN_SCOPE),
                "out_of_scope": data.get("out_of_scope", _DEFAULT_OUT_OF_SCOPE),
            }
        return {
            "in_scope": in_scope_seeds if in_scope_seeds is not None else _DEFAULT_IN_SCOPE,
            "out_of_scope": out_of_scope_seeds if out_of_scope_seeds is not None else _DEFAULT_OUT_OF_SCOPE,
        }

    def _embed_all(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384))
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return np.array(embeddings)

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()

        if not text.strip():
            return ValidatorResult(
                passed=True,
                category="out_of_scope",
                score=None,
                details={
                    "closest_in_scope": None,
                    "closest_out_of_scope": None,
                    "scores": {"max_in": 0.0, "max_out": 0.0},
                    "threshold_in": self.threshold_in,
                    "threshold_out": self.threshold_out,
                    "margin": self.margin,
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            query_vec = self._model.encode([text], normalize_embeddings=True)[0]
        except Exception:
            return ValidatorResult(
                passed=False,
                category="out_of_scope",
                score=1.0,
                details={
                    "error": "embedding_failed",
                    "stage": "out_of_scope_embed",
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        max_in = 0.0
        closest_in: str | None = None
        if len(self._in_embeddings) > 0:
            sims_in = np.dot(self._in_embeddings, query_vec)
            idx_in = int(np.argmax(sims_in))
            max_in = float(sims_in[idx_in])
            closest_in = self._in_scope_seeds[idx_in]

        max_out = 0.0
        closest_out: str | None = None
        if len(self._out_embeddings) > 0:
            sims_out = np.dot(self._out_embeddings, query_vec)
            idx_out = int(np.argmax(sims_out))
            max_out = float(sims_out[idx_out])
            closest_out = self._out_of_scope_seeds[idx_out]

        blocked = False

        if max_in < self.threshold_in and max_out > self.threshold_out:
            blocked = True

        if max_out > max_in + self.margin:
            blocked = True

        details: dict[str, Any] = {
            "closest_in_scope": closest_in,
            "closest_out_of_scope": closest_out,
            "scores": {"max_in": max_in, "max_out": max_out},
            "threshold_in": self.threshold_in,
            "threshold_out": self.threshold_out,
            "margin": self.margin,
        }

        if blocked:
            details["fallback_message"] = FALLBACK_MESSAGE

        return ValidatorResult(
            passed=not blocked,
            category="out_of_scope",
            score=float(max_out) if blocked else None,
            details=details,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
