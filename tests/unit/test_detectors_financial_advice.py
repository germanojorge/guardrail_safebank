"""
Unit tests — FinancialAdviceDetector (R1 e R2 da rubrica).

WARNING: Closed-loop fixtures (building-rigorously.md §1). As regex, as
fixtures e o mapeamento foram escritos pelo mesmo agente. Testes validam
consistência interna, não cobertura contra realidade externa.
Bypasses conhecidos marcados como xfail.
"""

import pytest

from guardrails.detectors.financial_advice import FinancialAdviceDetector

_d = FinancialAdviceDetector()


# ---------------------------------------------------------------------------
# R1 — Promessa de rentabilidade
# ---------------------------------------------------------------------------


def test_r1_rendimento_garantido():
    r = _d.detect("Seu investimento tem rendimento garantido de 12% ao ano.")
    assert r.detected
    assert r.rule_id == "promessa_rentabilidade"


def test_r1_garantia_retorno():
    r = _d.detect("Garantimos retorno de 8% ao mês nessa aplicação.")
    assert r.detected
    assert r.rule_id == "promessa_rentabilidade"


def test_r2_minimizacao_risco():
    r = _d.detect("Esse produto é sem risco, você não perde nada.")
    assert r.detected
    assert r.rule_id == "minimizacao_risco"


def test_r2_risco_zero():
    r = _d.detect("Risco zero! Invista sem medo.")
    assert r.detected
    assert r.rule_id == "minimizacao_risco"


# ---------------------------------------------------------------------------
# R2 — Recomendação direta
# ---------------------------------------------------------------------------


def test_r2_recomendo():
    r = _d.detect("Te recomendo investir no CDB Premium agora.")
    assert r.detected
    assert r.rule_id == "recomendacao_direta"


def test_r2_invista_agora():
    r = _d.detect("Invista agora no Fundo de Renda Fixa!")
    assert r.detected
    assert r.rule_id == "recomendacao_direta"


def test_r2_alocacao_indevida():
    r = _d.detect("Coloque tudo no CDB, não vai se arrepender.")
    assert r.detected
    assert r.rule_id == "alocacao_indevida"


def test_r2_comparacao_absoluta():
    r = _d.detect("Melhor investimento do mercado, superior a todos os outros.")
    assert r.detected
    assert r.rule_id == "comparacao_absoluta"


def test_r2_urgencia():
    r = _d.detect("Só hoje! Última chance de investir nessa oferta por tempo limitado.")
    assert r.detected
    assert r.rule_id == "urgencia"


# ---------------------------------------------------------------------------
# Casos benignos (não devem disparar)
# ---------------------------------------------------------------------------


def test_benign_saldo_query():
    r = _d.detect("Qual o meu saldo disponível?")
    assert not r.detected


def test_benign_explicacao_cdb():
    r = _d.detect("O CDB é um título de renda fixa emitido por bancos.")
    assert not r.detected


def test_benign_pix_info():
    r = _d.detect("Como faço um Pix para outra conta?")
    assert not r.detected


# ---------------------------------------------------------------------------
# Bypasses conhecidos — falham por design (closed-loop / paraphrase)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Paráfrase não coberta: regex não detecta promessa implícita sem léxico direto. building-rigorously.md §1: closed-loop fixture. LIMITATIONS.md §Rule-Based.")
def test_xfail_paraphrase_guaranteed():
    # "histórico consistente de valorização" ≈ rentabilidade garantida (tom, sem léxico)
    r = _d.detect("Esse fundo tem histórico consistente de valorização ano após ano.")
    assert r.detected


@pytest.mark.xfail(reason="Negação implícita: 'não é sem risco' deveria NÃO disparar minimizacao_risco mas o faz. Regex match 'sem risco' dentro da string. LIMITATIONS.md §Rule-Based.")
def test_xfail_negation_risk():
    # Frase legítima que contém "sem risco" mas com negação
    r = _d.detect("Não existe produto sem risco no mercado financeiro.")
    assert not r.detected
