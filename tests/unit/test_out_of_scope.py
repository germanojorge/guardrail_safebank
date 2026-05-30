"""
Unit tests for OutOfScopeValidator — cosine similarity against seed banks.

Heavy tests (loading real MiniLM model) are gated behind @pytest.mark.slow
and also respect SKIP_HEAVY_TESTS env var.
"""

import os

import numpy as np
import pytest

from guardrails.validators import OutOfScopeValidator, Validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pre-normalized reference vectors (d=384 → normalized to unit length).
# in_vec_canonical: close to banking domain
# out_vec_canonical: close to non-banking domain
# ambi_vec: somewhere in between

_D = 384

_IN_VEC = np.ones(_D) / np.sqrt(_D)  # unit vector, all positive
_OUT_VEC = -_IN_VEC  # opposite direction


class _SeedAwareMock:
    """Mock embedding model that returns different vectors by call order.

    - First call (in_scope seeds): returns in_v for each seed
    - Second call (out_of_scope seeds): returns out_v for each seed
    - Subsequent calls (query): returns query_v
    """

    def __init__(self, in_v: np.ndarray, out_v: np.ndarray, query_v: np.ndarray):
        self._in = in_v
        self._out = out_v
        self._q = query_v
        self._seed_call = 0
        self.encode = self._encode

    def _encode(self, texts, normalize_embeddings=True):
        if isinstance(texts, str):
            return self._q
        # Assume seed calls come first (from constructor), then query calls (from run)
        if self._seed_call < 2 and len(texts) > 1:
            self._seed_call += 1
            vec = self._in if self._seed_call == 1 else self._out
            return np.tile(vec, (len(texts), 1))
        # Query call or single-item seed call
        return np.array([self._q])


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------


def test_validator_protocol_runtime_check():
    """OutOfScopeValidator satisfies the Validator Protocol at runtime."""
    m = _SeedAwareMock(_IN_VEC, _OUT_VEC, _IN_VEC)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )
    assert isinstance(v, Validator)


# ---------------------------------------------------------------------------
# Fast tests — mock embeddings
# ---------------------------------------------------------------------------


def test_in_scope_passes():
    """Banking question passes (high in-scope similarity)."""
    query = _IN_VEC
    m = _SeedAwareMock(_IN_VEC, _OUT_VEC, query)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )
    result = v.run("Como faço um Pix?")
    assert result.passed is True


def test_out_of_scope_blocks():
    """Non-banking question blocks (low in-scope, high out-of-scope)."""
    query = _OUT_VEC
    m = _SeedAwareMock(_IN_VEC, _OUT_VEC, query)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )
    result = v.run("Como fazer bolo de chocolate?")
    assert result.passed is False
    assert result.category == "out_of_scope"


def test_details_shape():
    """Block result has correct details shape, pass result has scores."""
    query = _OUT_VEC
    m = _SeedAwareMock(_IN_VEC, _OUT_VEC, query)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )

    result = v.run("Como fazer bolo de chocolate?")
    assert "closest_in_scope" in result.details
    assert "closest_out_of_scope" in result.details
    assert "scores" in result.details
    assert "max_in" in result.details["scores"]
    assert "max_out" in result.details["scores"]
    assert "threshold_in" in result.details
    assert "threshold_out" in result.details
    assert "margin" in result.details
    assert "fallback_message" in result.details


def test_passed_result_shape():
    """Pass result has correct details shape (no fallback_message)."""
    query = _IN_VEC
    m = _SeedAwareMock(_IN_VEC, _OUT_VEC, query)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )

    result = v.run("Como faço um Pix?")
    assert "closest_in_scope" in result.details
    assert "closest_out_of_scope" in result.details
    assert "scores" in result.details


def test_empty_text_passes():
    """Empty text passes without additional encode calls."""
    m = _SeedAwareMock(_IN_VEC, _OUT_VEC, _IN_VEC)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )
    result = v.run("  ")
    assert result.passed is True


def test_embedding_error_fail_closed():
    """Embedding failure in run() produces block (fail-closed).

    Seed embedding in __init__ must succeed; only runtime encode fails.
    """
    in_v = _IN_VEC
    out_v = _OUT_VEC

    class _FailOnQuery:
        def __init__(self, in_v, out_v):
            self._in = in_v
            self._out = out_v
            self._seed_call = 0

        def encode(self, texts, normalize_embeddings=True):
            if isinstance(texts, str):
                raise RuntimeError("model crash")
            if len(texts) > 1 and self._seed_call < 2:
                self._seed_call += 1
                vec = self._in if self._seed_call == 1 else self._out
                return np.tile(vec, (len(texts), 1))
            raise RuntimeError("model crash")

    m = _FailOnQuery(in_v, out_v)
    v = OutOfScopeValidator(
        embedding_model=m,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )
    result = v.run("Algum texto.")
    assert result.passed is False
    assert result.details.get("error") == "embedding_failed"


# ---------------------------------------------------------------------------
# Threshold logic tests
# ---------------------------------------------------------------------------


def test_margin_block_logic():
    """Block when max_out > max_in + margin even if both are below individual thresholds."""
    far_v = np.zeros(_D)
    far_v[0] = 1.0
    close_v = _IN_VEC

    m = _SeedAwareMock(far_v, close_v, close_v)
    v = OutOfScopeValidator(
        embedding_model=m,
        threshold_in=0.30,
        threshold_out=0.95,
        margin=0.15,
        in_scope_seeds=["Como faço um Pix?", "Qual o saldo?"],
        out_of_scope_seeds=["Como fazer bolo?", "Receita de pão."],
    )
    result = v.run("Pergunta ambígua.")
    assert result.passed is False, f"Expected block, got {result.details['scores']}"


# ---------------------------------------------------------------------------
# Slow tests — real MiniLM model
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping MiniLM model tests",
)
def test_real_in_scope():
    """Banking queries pass the real OutOfScopeValidator."""
    v = OutOfScopeValidator()
    banking_queries = [
        "Como faço um Pix?",
        "Qual o saldo da minha conta corrente?",
        "Quero abrir uma conta poupança.",
        "Quais são as tarifas do cartão de crédito?",
        "Como faço para aumentar o limite do cartão?",
        "Preciso de segunda via do boleto.",
        "Como consulto o extrato bancário?",
        "Quero fazer uma transferência TED.",
        "Qual a taxa de juros do empréstimo pessoal?",
        "Como cadastrar uma chave Pix?",
    ]
    passed = 0
    for q in banking_queries:
        result = v.run(q)
        if result.passed:
            passed += 1
    assert passed >= 7, f"Only {passed}/10 banking queries passed"


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping MiniLM model tests",
)
def test_real_out_of_scope():
    """Non-banking queries are blocked by the real OutOfScopeValidator."""
    v = OutOfScopeValidator()
    non_banking = [
        "Como fazer bolo de chocolate?",
        "Me ensina a programar em Python.",
        "Como fazer exercícios de musculação?",
        "Qual a fórmula química da água?",
        "Escreva um poema sobre o mar.",
        "O que é computação quântica?",
        "Como fazer pão caseiro?",
        "Previsão do tempo para amanhã?",
        "Como fazer café expresso?",
        "Receita de brigadeiro caseiro.",
    ]
    blocked = 0
    for q in non_banking:
        result = v.run(q)
        if not result.passed:
            blocked += 1
    assert blocked >= 7, f"Only {blocked}/10 non-banking queries blocked"


@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("SKIP_HEAVY_TESTS")),
    reason="SKIP_HEAVY_TESTS set — skipping MiniLM model tests",
)
def test_real_latency():
    """Embedding + comparison completes in < 100ms."""
    v = OutOfScopeValidator()
    result = v.run("Como faço um Pix?")
    assert result.latency_ms is not None
    assert result.latency_ms < 100, f"OutOfScope latency {result.latency_ms:.1f}ms >= 100ms"
