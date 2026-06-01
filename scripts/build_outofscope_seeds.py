#!/usr/bin/env python3
"""Extract in-scope seeds from Itaú FAQ dataset.

Loads `Itau-Unibanco/FAQ_BACEN`, extracts unique banking questions,
and saves alongside hardcoded out-of-scope seeds to data/out_of_scope_seeds.json.

Fallback: if the Itaú dataset is unavailable, uses the built-in seed lists
defined in guardrails/validators/out_of_scope.py.
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de importar datasets/transformers

import json
import os


def load_itau_faq() -> list[str]:
    print("Loading Itau-Unibanco/FAQ_BACEN ...")
    from datasets import load_dataset

    ds = load_dataset("Itau-Unibanco/FAQ_BACEN", split="train")
    questions: list[str] = []
    for row in ds:
        q = row.get("pergunta", "").strip()
        if q:
            questions.append(q)
    return questions


_OUT_OF_SCOPE_SEEDS: list[str] = [
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
    "Previsão do tempo para amanhã?",
    "Como fazer café expresso?",
    "Quem é o atual presidente do Brasil?",
    "Como cuidar de uma samambaia?",
    "Receita de brigadeiro caseiro.",
    "O que significa a palavra resiliência?",
    "Como tocar violão para iniciantes?",
    "Qual o melhor restaurante japonês em São Paulo?",
    "Como fazer origami de tsuru?",
    "História da Segunda Guerra Mundial.",
]


def main() -> None:
    try:
        questions = load_itau_faq()
    except Exception as e:
        print(f"Itaú FAQ dataset unavailable ({e})")
        print("Skipping dataset extraction — using built-in seeds instead.")
        questions = []

    if questions:
        unique = list(dict.fromkeys(questions))
        print(f"Loaded {len(questions)} questions, {len(unique)} unique")
        in_scope = unique[:50]
    else:
        from guardrails.validators.out_of_scope import _DEFAULT_IN_SCOPE

        in_scope = _DEFAULT_IN_SCOPE
        print(f"Using {len(in_scope)} built-in in-scope seeds")

    output = {
        "in_scope": in_scope,
        "out_of_scope": _OUT_OF_SCOPE_SEEDS,
    }

    os.makedirs("data", exist_ok=True)
    with open("data/out_of_scope_seeds.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Saved data/out_of_scope_seeds.json")
    print(f"  in_scope seeds: {len(in_scope)}")
    print(f"  out_of_scope seeds: {len(_OUT_OF_SCOPE_SEEDS)}")


if __name__ == "__main__":
    main()
