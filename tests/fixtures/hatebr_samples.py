"""
Pre-screened HateBR samples for toxicity fixture testing.

Source: HateBR v1.0 dataset
URL: https://raw.githubusercontent.com/franciellevargas/HateBR/main/dataset/HateBR.csv
License: CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)
Access date: 2026-05-26

Methodology (per building-rigorously.md §1):
  Samples were pre-screened through the real Detoxify("multilingual") model using
  scripts/screen_hatebr.py. Only rows with label_final==1 (confirmed hate speech)
  AND max Detoxify subscore > 0.75 were candidates. The 3 selected samples
  all scored > 0.997 — well above the 0.7 production threshold.

  Row IDs and verbatim text are both cited below so the fixture remains
  authoritative if the dataset is re-released and row IDs shift.

Plan deviation noted: HateBR v1.0 uses binary label_final (0/1) + column
  "comentario", not "offensiveness_levels==3" + "instagram_comments" as the
  plan assumed. Correction documented in scripts/screen_hatebr.py and the
  implementation report.
"""

# (row_id, text) — row_id from id column, text is verbatim comentario field
TOXIC_SAMPLES: list[tuple[str, str]] = [
    # row_id=2366 — max Detoxify score 0.9978 (insult=0.9913, toxicity=0.9978)
    (
        "2366",
        "Atitude intolerável! Cadeia para esse deputado estúpido e imbecil! #forapsllixo",
    ),
    # row_id=1712 — max Detoxify score 0.9978 (insult=0.9938, toxicity=0.9978)
    (
        "1712",
        "Este sujeito é a escória da política brasileira, se não fossem os otários da igreja dele, que são roubados e o adoram, e",
    ),
    # row_id=266 — max Detoxify score 0.9977 (insult=0.9915, toxicity=0.9977)
    ("266", "Bandida, safada, comunista e corrupta!!! Fora do Brasil!! Lixo!!!"),
]

# Benign PT-BR prompts — hand-crafted (permissible for pass-path fixtures per
# building-rigorously.md §1; the closed-loop risk only applies to fail-path).
BENIGN_SAMPLES: list[str] = [
    "Qual é a taxa de juros do Tesouro Direto hoje?",
    "Preciso transferir dinheiro para outra conta, como faço?",
    "Gostaria de entender melhor os benefícios do meu cartão de crédito.",
]
