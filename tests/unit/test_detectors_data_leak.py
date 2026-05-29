"""
Unit tests — DataLeakDetector (R4 da rubrica).

WARNING: Closed-loop fixtures (building-rigorously.md §1). As regex, as
fixtures e o mapeamento foram escritos pelo mesmo agente.
Bypasses conhecidos marcados como xfail.
"""

import pytest

from guardrails.detectors.data_leak import DataLeakDetector

_d = DataLeakDetector()


# ---------------------------------------------------------------------------
# Padrões estruturais de credenciais
# ---------------------------------------------------------------------------


def test_structural_api_key():
    r = _d.detect("Minha api_key é abc123xyz456def789ghi012.")
    assert r.detected
    assert r.rule_id == "structural_credential"


def test_structural_jwt():
    r = _d.detect("Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
    assert r.detected
    assert r.rule_id == "structural_credential"


def test_structural_aws_key():
    r = _d.detect("AKIAIOSFODNN7EXAMPLE é minha chave AWS.")
    assert r.detected
    assert r.rule_id == "structural_credential"


def test_structural_internal_url():
    r = _d.detect("O endpoint interno é http://192.168.1.100/api/v1/accounts")
    assert r.detected
    assert r.rule_id == "structural_credential"


# ---------------------------------------------------------------------------
# Co-ocorrência: palavra sensível + verbo de exposição
# ---------------------------------------------------------------------------


def test_sensitive_exposure_system_prompt():
    r = _d.detect("Posso revelar o system prompt para você.")
    assert r.detected
    assert r.rule_id == "sensitive_exposure"


def test_sensitive_exposure_instrucao():
    r = _d.detect("Vou mostrar a instrução do sistema que recebi.")
    assert r.detected
    assert r.rule_id == "sensitive_exposure"


def test_sensitive_exposure_credencial():
    r = _d.detect("Posso compartilhar a credencial de acesso ao sistema.")
    assert r.detected
    assert r.rule_id == "sensitive_exposure"


# ---------------------------------------------------------------------------
# Casos benignos
# ---------------------------------------------------------------------------


def test_benign_saldo():
    r = _d.detect("Qual o meu saldo na conta corrente?")
    assert not r.detected


def test_benign_ajuda_pix():
    r = _d.detect("Como faço para enviar um Pix?")
    assert not r.detected


def test_benign_sensitive_word_without_verb():
    # Contém palavra sensível mas sem verbo de exposição na janela
    r = _d.detect("O system prompt de IA geralmente define o comportamento do assistente.")
    assert not r.detected


# ---------------------------------------------------------------------------
# Bypasses conhecidos
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Paráfrase: 'segredo do sistema' não está na lista de _SENSITIVE_WORDS. building-rigorously.md §1. LIMITATIONS.md §Rule-Based.")
def test_xfail_secret_paraphrase():
    r = _d.detect("Vou divulgar o segredo do sistema para você.")
    assert r.detected


@pytest.mark.xfail(reason="Obfuscação: espaços/separadores em JWT impedem match do padrão estrutural. building-rigorously.md §2 (encoding bypass). LIMITATIONS.md §Rule-Based.")
def test_xfail_obfuscated_jwt():
    r = _d.detect("Token: eyJ hbGci OiJ IUzI 1NiJ9.payload.sig")
    assert r.detected
