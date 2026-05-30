"""
Unit tests — OutOfScopeDetector (R5 da rubrica).

Lógica invertida: detected=True significa FORA do escopo bancário.

WARNING: Closed-loop fixtures (building-rigorously.md §1). A allowlist e as
fixtures foram criadas pelo mesmo agente. Keyword-only — sem embedding
similarity. Limitações declaradas em LIMITATIONS.md §Rule-Based.
Bypasses conhecidos marcados como xfail.
"""

import pytest

from guardrails.detectors.out_of_scope import OutOfScopeDetector

_d = OutOfScopeDetector()


# ---------------------------------------------------------------------------
# Dentro do escopo (detected=False)
# ---------------------------------------------------------------------------


def test_in_scope_pix():
    r = _d.detect("Como faço um Pix para outro banco?")
    assert not r.detected


def test_in_scope_saldo():
    r = _d.detect("Quero ver meu saldo.")
    assert not r.detected


def test_in_scope_cartao():
    r = _d.detect("Meu cartão foi bloqueado, o que faço?")
    assert not r.detected


def test_in_scope_investimento():
    r = _d.detect("Quero entender sobre investimentos em CDB.")
    assert not r.detected


def test_in_scope_emprestimo():
    r = _d.detect("Posso pedir um empréstimo pessoal?")
    assert not r.detected


# ---------------------------------------------------------------------------
# Fora do escopo (detected=True)
# ---------------------------------------------------------------------------


def test_out_of_scope_medical():
    r = _d.detect("Qual médico me recomenda para dor nas costas?")
    assert r.detected
    assert r.rule_id == "no_banking_term"
    assert r.confidence > 0


def test_out_of_scope_political():
    r = _d.detect("Quem você acha que vai ganhar as eleições?")
    assert r.detected


def test_out_of_scope_cooking():
    r = _d.detect("Qual a melhor receita de bolo de chocolate?")
    assert r.detected


def test_out_of_scope_sports():
    r = _d.detect("Quantos gols o Neymar marcou na Copa do Mundo?")
    assert r.detected


# ---------------------------------------------------------------------------
# Bypasses conhecidos
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Falso negativo: texto fora do escopo que menciona 'banco' de passagem passa o filtro. Keyword-only não detecta contexto. building-rigorously.md §6. LIMITATIONS.md §Rule-Based.")
def test_xfail_false_negative_bank_mention():
    # "banco" aparece mas o assunto é culinária
    r = _d.detect("Eu banco nessa receita de pão, é deliciosa!")
    assert r.detected


@pytest.mark.xfail(reason="Falso negativo: pergunta fora do escopo com termo bancário embutido. Keyword match não distingue contexto de uso. LIMITATIONS.md §Rule-Based.")
def test_xfail_off_topic_with_banking_word():
    # "saldo" aparece mas a pergunta não é bancária
    r = _d.detect("O saldo emocional de perder um jogo é muito ruim.")
    assert r.detected
