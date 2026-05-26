"""
Hand-crafted PT-BR PII fixtures for PIIValidator testing.

WARNING — closed-loop risk (building-rigorously.md §1): these fixtures were authored
by the same agent that wrote the regex patterns. They demonstrate pattern coverage but
do NOT provide adversarial breadth. No external PT-BR PII corpus was available at MVP
scope. See LIMITATIONS.md for declared gaps (phone format misses, checksum absence, etc.).
"""

import pytest

# Plain PT-BR strings with no PII — used to verify the pass-path
BENIGN_SAMPLES: list[str] = [
    "Qual é o limite do cartão Gold?",
    "Meu cartão foi bloqueado, como desbloqueio?",
    "Quero saber sobre o programa de pontos",
    "Como faço para solicitar um empréstimo pessoal?",
]

# (case_id, expected_entity_type, text) — used to verify the fail-path
PII_SAMPLES: list[tuple[str, str, str]] = [
    ("cpf_formatted", "cpf", "Meu CPF é 123.456.789-09 para cadastro."),
    ("card_dashed", "cartao", "Meu cartão é 4111-1111-1111-1111, pode confirmar?"),
    ("card_spaced", "cartao", "Cartão 4111 1111 1111 1111"),
    ("email_simple", "email", "Mande para joao.silva@example.com.br"),
    ("phone_dashed", "telefone", "Liga no 011-912-3456"),
    # 11-digit mobile numbers without formatting miss the 10-digit phone regex.
    # Documented in LIMITATIONS.md; kept here as an explicit known gap.
    pytest.param(
        "phone_plain",
        "telefone",
        "Meu fone é 11912345678",
        marks=pytest.mark.xfail(
            reason="11-digit mobile numbers without formatting miss the 10-digit phone regex; see LIMITATIONS.md"
        ),
    ),
    # 9-digit local numbers also miss the phone regex.
    pytest.param(
        "phone_9digit_local",
        "telefone",
        "Meu telefone é 912345678",
        marks=pytest.mark.xfail(
            reason="9-digit local numbers miss the 10-digit phone regex; see LIMITATIONS.md"
        ),
    ),
    # CPF without dots/dash (plain 11 digits) misses the CPF regex.
    pytest.param(
        "cpf_unformatted",
        "cpf",
        "Meu CPF é 12345678909",
        marks=pytest.mark.xfail(
            reason="CPF without formatting (plain 11 digits) misses the CPF regex; see LIMITATIONS.md"
        ),
    ),
]
