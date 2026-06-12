"""
Unit tests for scripts/eval_retrieval.py.

All tests here are fast: no real model downloads, no network calls.
Mock fixtures replace SentenceTransformer and frozen JSONL files.

The @pytest.mark.slow test loads the real e5-small model (skipped in CI by default).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

# Ensure scripts/ is importable regardless of pytest working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from scripts.eval_retrieval import (  # noqa: E402
    apply_prefixes,
    extract_metrics,
    load_frozen,
    render_markdown,
    write_run_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ir_results(name: str = "faq_bacen") -> dict[str, float]:
    """Build a synthetic InformationRetrievalEvaluator results dict."""
    return {
        f"{name}_cosine_recall@1": 0.50,
        f"{name}_cosine_recall@3": 0.70,
        f"{name}_cosine_recall@5": 0.80,
        f"{name}_cosine_recall@10": 0.90,
        f"{name}_cosine_mrr@10": 0.60,
        f"{name}_cosine_ndcg@10": 0.65,
        f"{name}_cosine_map@10": 0.55,
        # noise keys that should be ignored
        f"{name}_cosine_accuracy@1": 0.99,
        f"{name}_cosine_precision@1": 0.99,
    }


# ---------------------------------------------------------------------------
# extract_metrics
# ---------------------------------------------------------------------------


def test_extract_metrics_maps_all_keys():
    results = _make_ir_results("faq_bacen")
    metrics = extract_metrics(results, "faq_bacen")

    assert metrics["recall@1"] == 0.50
    assert metrics["recall@3"] == 0.70
    assert metrics["recall@5"] == 0.80
    assert metrics["recall@10"] == 0.90
    assert metrics["mrr@10"] == 0.60
    assert metrics["ndcg@10"] == 0.65
    assert metrics["map@10"] == 0.55


def test_extract_metrics_ignores_noise_keys():
    results = _make_ir_results("faq_bacen")
    metrics = extract_metrics(results, "faq_bacen")
    # Accuracy and precision are noise — should not appear
    assert "accuracy@1" not in metrics
    assert "precision@1" not in metrics


def test_extract_metrics_rounds_to_4_places():
    results = {"faq_bacen_cosine_recall@1": 0.123456789}
    metrics = extract_metrics(results, "faq_bacen")
    assert metrics["recall@1"] == round(0.123456789, 4)


def test_extract_metrics_missing_keys_are_skipped():
    """If evaluator omits a metric key, extract_metrics skips it gracefully."""
    results = {"faq_bacen_cosine_recall@1": 0.5}
    metrics = extract_metrics(results, "faq_bacen")
    assert "recall@1" in metrics
    assert "mrr@10" not in metrics


def test_extract_metrics_respects_name_param():
    results = _make_ir_results("banking_kb")
    metrics = extract_metrics(results, "banking_kb")
    assert metrics["recall@1"] == 0.50


def test_extract_metrics_different_name_not_cross_picked():
    """Keys named with a different name prefix should not match."""
    results = _make_ir_results("banking_kb")
    metrics = extract_metrics(results, "faq_bacen")
    # All keys are 'banking_kb_*', so nothing should match 'faq_bacen_*'
    assert len(metrics) == 0


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


def test_render_markdown_has_header_and_separator():
    metrics = {"recall@1": 0.50, "mrr@10": 0.60}
    table = render_markdown(metrics)
    lines = table.splitlines()
    assert lines[0].startswith("| Metric")
    assert "---" in lines[1]


def test_render_markdown_contains_all_metrics():
    metrics = {"recall@1": 0.50, "recall@10": 0.90, "mrr@10": 0.60, "ndcg@10": 0.65, "map@10": 0.55}
    table = render_markdown(metrics)
    for key in metrics:
        assert key in table


def test_render_markdown_formats_floats_4_places():
    metrics = {"recall@1": 0.5}
    table = render_markdown(metrics)
    assert "0.5000" in table


def test_render_markdown_rows_are_sorted():
    metrics = {"recall@10": 0.9, "map@10": 0.5, "recall@1": 0.5}
    table = render_markdown(metrics)
    rows = [ln for ln in table.splitlines() if ln.startswith("|") and "---" not in ln and "Metric" not in ln]
    keys_in_order = [r.split("|")[1].strip() for r in rows]
    assert keys_in_order == sorted(keys_in_order)


# ---------------------------------------------------------------------------
# load_frozen — faq_bacen path
# ---------------------------------------------------------------------------


def test_load_frozen_faq_bacen_reads_jsonl(tmp_path):
    corpus_path = tmp_path / "faq_bacen_corpus.jsonl"
    corpus_path.write_text(
        '{"doc_id": "test_0", "text": "Resposta gold."}\n{"doc_id": "train_0", "text": "Resposta distractor."}\n',
        encoding="utf-8",
    )
    eval_path = tmp_path / "faq_bacen_eval.jsonl"
    eval_path.write_text(
        '{"query_id": "q_0", "query": "Pergunta teste?", "relevant_doc_ids": ["test_0"]}\n',
        encoding="utf-8",
    )

    corpus, queries, relevant_docs = load_frozen("faq_bacen", data_dir=str(tmp_path))

    assert len(corpus) == 2
    assert corpus["test_0"] == "Resposta gold."
    assert len(queries) == 1
    assert queries["q_0"] == "Pergunta teste?"
    assert relevant_docs["q_0"] == {"test_0"}


def test_load_frozen_faq_bacen_multiple_relevant_docs(tmp_path):
    (tmp_path / "faq_bacen_corpus.jsonl").write_text(
        '{"doc_id": "test_0", "text": "A"}\n{"doc_id": "test_1", "text": "B"}\n',
        encoding="utf-8",
    )
    (tmp_path / "faq_bacen_eval.jsonl").write_text(
        '{"query_id": "q_0", "query": "Q?", "relevant_doc_ids": ["test_0", "test_1"]}\n',
        encoding="utf-8",
    )
    _, _, relevant_docs = load_frozen("faq_bacen", data_dir=str(tmp_path))
    assert relevant_docs["q_0"] == {"test_0", "test_1"}


def test_load_frozen_unknown_dataset_raises(tmp_path):
    with pytest.raises(ValueError, match="Unknown dataset"):
        load_frozen("unknown_dataset", data_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# load_frozen — banking_kb path (uses real data/banking_kb + data/eval)
# ---------------------------------------------------------------------------


def test_load_frozen_banking_kb_no_orphan_ids():
    """All relevant_doc_ids in banking_kb_eval.jsonl must exist in the derived corpus."""
    corpus, queries, relevant_docs = load_frozen("banking_kb")
    orphans = [(qid, did) for qid, doc_ids in relevant_docs.items() for did in doc_ids if did not in corpus]
    assert len(orphans) == 0, f"Orphan ids found: {orphans}"


def test_load_frozen_banking_kb_skips_comment_lines(tmp_path):
    """Comment lines starting with # must be skipped."""
    (tmp_path / "banking_kb_eval.jsonl").write_text(
        '# this is a comment\n{"query_id": "bk_q0", "query": "test?", "relevant_doc_ids": ["fake-id"]}\n',
        encoding="utf-8",
    )
    # Also need a corpus — patch _split_paragraphs to return something with the fake-id
    # instead of importing from ingest_banking_kb, monkeypatch at module level
    import uuid

    NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    fake_id = str(uuid.uuid5(NAMESPACE, "fake.md:0"))

    eval_path = tmp_path / "banking_kb_eval.jsonl"
    eval_path.write_text(
        f'# this is a comment\n{{"query_id": "bk_q0", "query": "test?", "relevant_doc_ids": ["{fake_id}"]}}\n',
        encoding="utf-8",
    )

    # Create a minimal .md file so the corpus contains the fake_id
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    (kb_dir / "fake.md").write_text("Some paragraph content here.", encoding="utf-8")

    corpus, queries, relevant_docs = load_frozen("banking_kb", data_dir=str(tmp_path), kb_dir=str(kb_dir))
    assert "bk_q0" in queries
    assert len(queries) == 1


# ---------------------------------------------------------------------------
# freeze_faq_bacen determinism
# ---------------------------------------------------------------------------


def test_freeze_writes_corpus_sorted_by_doc_id(tmp_path, monkeypatch):
    """freeze_faq_bacen writes corpus rows sorted by doc_id for determinism."""
    from scripts.eval_retrieval import freeze_faq_bacen

    def _mock_load():
        corpus = {"test_10": "C", "test_2": "B", "test_1": "A", "train_0": "D"}
        return [], corpus, ["Q1", "Q2"], ["test_1", "test_2"]

    monkeypatch.setattr("scripts.eval_retrieval._load_faq_data", _mock_load)
    freeze_faq_bacen(str(tmp_path))

    lines = (tmp_path / "faq_bacen_corpus.jsonl").read_text(encoding="utf-8").strip().splitlines()
    doc_ids = [json.loads(ln)["doc_id"] for ln in lines]
    assert doc_ids == sorted(doc_ids)


def test_freeze_writes_eval_sorted_by_doc_suffix(tmp_path, monkeypatch):
    """freeze_faq_bacen writes eval rows sorted by numeric doc_id suffix."""
    from scripts.eval_retrieval import freeze_faq_bacen

    def _mock_load():
        corpus = {"test_0": "A", "test_1": "B", "test_10": "C"}
        queries = ["Q10", "Q1", "Q0"]
        relevant_docs = ["test_10", "test_1", "test_0"]
        return [], corpus, queries, relevant_docs

    monkeypatch.setattr("scripts.eval_retrieval._load_faq_data", _mock_load)
    freeze_faq_bacen(str(tmp_path))

    lines = (tmp_path / "faq_bacen_eval.jsonl").read_text(encoding="utf-8").strip().splitlines()
    doc_ids = [json.loads(ln)["relevant_doc_ids"][0] for ln in lines]
    # Should be test_0, test_1, test_10 (numeric sort, not lexicographic)
    suffixes = [int(did.split("_")[1]) for did in doc_ids]
    assert suffixes == sorted(suffixes)


# ---------------------------------------------------------------------------
# write_run_json
# ---------------------------------------------------------------------------


def test_write_run_json_creates_valid_file(tmp_path):
    payload = {
        "model": "intfloat/multilingual-e5-small",
        "dataset": "faq_bacen",
        "prefixes_applied": True,
        "closed_loop": False,
        "n_queries": 10,
        "n_corpus": 100,
        "timestamp": "2026-06-11T12:00:00Z",
        "seed": 42,
        "metrics": {"recall@1": 0.5},
    }
    out_path = write_run_json(str(tmp_path), payload)

    assert out_path.exists()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["prefixes_applied"] is True
    assert loaded["metrics"]["recall@1"] == 0.5


def test_write_run_json_filename_encodes_model_and_dataset(tmp_path):
    payload = {
        "model": "intfloat/multilingual-e5-small",
        "dataset": "faq_bacen",
        "prefixes_applied": True,
        "closed_loop": False,
        "n_queries": 1,
        "n_corpus": 1,
        "timestamp": "2026-06-11T12:30:00Z",
        "seed": 42,
        "metrics": {},
    }
    out_path = write_run_json(str(tmp_path), payload)
    assert "faq_bacen" in out_path.name
    assert "intfloat" in out_path.name


# ---------------------------------------------------------------------------
# apply_prefixes (pure function — network-free)
# ---------------------------------------------------------------------------


def test_apply_prefixes_e5_adds_query_prefix():
    texts = {"q_0": "qual meu saldo?", "q_1": "como faço pix?"}
    result = apply_prefixes(texts, "query", "e5")
    assert result["q_0"] == "query: qual meu saldo?"
    assert result["q_1"] == "query: como faço pix?"


def test_apply_prefixes_e5_adds_passage_prefix():
    texts = {"d_0": "Saldo disponível.", "d_1": "PIX é gratuito."}
    result = apply_prefixes(texts, "passage", "e5")
    assert result["d_0"] == "passage: Saldo disponível."
    assert result["d_1"] == "passage: PIX é gratuito."


def test_apply_prefixes_none_does_not_modify_texts():
    texts = {"q_0": "qual meu saldo?", "q_1": "como faço pix?"}
    result = apply_prefixes(texts, "query", "none")
    assert result == texts


def test_apply_prefixes_none_returns_new_dict():
    texts = {"q_0": "text"}
    result = apply_prefixes(texts, "query", "none")
    # Should be a copy, not the same object (defensive)
    assert result is not texts


def test_apply_prefixes_does_not_mutate_original():
    texts = {"q_0": "original"}
    apply_prefixes(texts, "query", "e5")
    assert texts["q_0"] == "original"


# ---------------------------------------------------------------------------
# run_eval prefix_style param (mock — network-free)
# ---------------------------------------------------------------------------


def test_run_eval_prefix_style_none_no_prefix(monkeypatch):
    """run_eval with prefix_style='none' must NOT prepend query:/passage:."""
    captured: dict[str, object] = {}

    class FakeEval:
        def __init__(self, *, queries, corpus, **kwargs):
            captured["queries"] = queries
            captured["corpus"] = corpus

        def __call__(self, model):
            return {}

    class FakeModel:
        pass

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())
    monkeypatch.setattr("scripts.eval_retrieval.InformationRetrievalEvaluator", FakeEval)

    from scripts.eval_retrieval import run_eval

    corpus = {"d_0": "Texto do documento."}
    queries = {"q_0": "Qual meu saldo?"}
    run_eval("fake-model", corpus, queries, {"q_0": {"d_0"}}, name="test", prefix_style="none")

    assert captured["corpus"]["d_0"] == "Texto do documento."
    assert captured["queries"]["q_0"] == "Qual meu saldo?"


def test_run_eval_prefix_style_e5_adds_prefixes(monkeypatch):
    """run_eval with prefix_style='e5' must prepend query:/passage:."""
    captured: dict[str, object] = {}

    class FakeEval:
        def __init__(self, *, queries, corpus, **kwargs):
            captured["queries"] = queries
            captured["corpus"] = corpus

        def __call__(self, model):
            return {}

    class FakeModel:
        pass

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())
    monkeypatch.setattr("scripts.eval_retrieval.InformationRetrievalEvaluator", FakeEval)

    from scripts.eval_retrieval import run_eval

    corpus = {"d_0": "Texto do documento."}
    queries = {"q_0": "Qual meu saldo?"}
    run_eval("fake-model", corpus, queries, {"q_0": {"d_0"}}, name="test", prefix_style="e5")

    assert captured["corpus"]["d_0"] == "passage: Texto do documento."
    assert captured["queries"]["q_0"] == "query: Qual meu saldo?"


def test_run_eval_invalid_prefix_style_raises(monkeypatch):
    """run_eval must raise ValueError for any prefix_style outside {e5, none}."""

    class FakeModel:
        pass

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())

    from scripts.eval_retrieval import run_eval

    with pytest.raises(ValueError, match="prefix_style"):
        run_eval("fake-model", {}, {}, {}, name="test", prefix_style="bert")


# ---------------------------------------------------------------------------
# write_run_json — prefix_style + latency_ms_per_query fields
# ---------------------------------------------------------------------------


def test_write_run_json_carries_prefix_style_and_latency(tmp_path):
    payload = {
        "model": "intfloat/multilingual-e5-small",
        "dataset": "faq_bacen",
        "prefix_style": "e5",
        "prefixes_applied": True,
        "closed_loop": False,
        "n_queries": 10,
        "n_corpus": 100,
        "timestamp": "2026-06-11T12:00:00Z",
        "seed": 42,
        "latency_ms_per_query": 12.345,
        "metrics": {"recall@5": 0.68},
    }
    out_path = write_run_json(str(tmp_path), payload)
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["prefix_style"] == "e5"
    assert loaded["latency_ms_per_query"] == 12.345


def test_write_run_json_prefix_style_none_prefixes_applied_false(tmp_path):
    payload = {
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "dataset": "faq_bacen",
        "prefix_style": "none",
        "prefixes_applied": False,
        "closed_loop": False,
        "n_queries": 10,
        "n_corpus": 100,
        "timestamp": "2026-06-11T13:00:00Z",
        "seed": 42,
        "latency_ms_per_query": 8.5,
        "metrics": {"recall@5": 0.55},
    }
    out_path = write_run_json(str(tmp_path), payload)
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["prefix_style"] == "none"
    assert loaded["prefixes_applied"] is False


# ---------------------------------------------------------------------------
# Slow / network tests (skipped in CI)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.network
def test_real_faq_bacen_recall_monotone():
    """Loads real e5-small, runs eval on frozen faq_bacen splits.

    Sanity: recall@1 <= recall@3 <= recall@5 <= recall@10.
    Registered as slow+network — skip with: uv run pytest -m 'not slow and not network'
    """
    from scripts.eval_retrieval import extract_metrics, load_frozen, run_eval

    corpus, queries, relevant_docs = load_frozen("faq_bacen")
    results = run_eval("intfloat/multilingual-e5-small", corpus, queries, relevant_docs, "faq_bacen")
    metrics = extract_metrics(results, "faq_bacen")

    assert metrics["recall@1"] <= metrics["recall@3"] <= metrics["recall@5"] <= metrics["recall@10"]
    # Not absurdly high (§3 building-rigorously: >0.95 at recall@1 would suggest leakage)
    assert metrics["recall@1"] < 0.95


# ---------------------------------------------------------------------------
# Pure IR metric helpers
# ---------------------------------------------------------------------------


from scripts.eval_retrieval import (  # noqa: E402
    average_precision,
    ndcg_at_k,
    rank_metrics,
    recall_at_k,
    reciprocal_rank,
)


# recall_at_k


def test_recall_at_k_hit_in_top_1():
    assert recall_at_k(["doc_0", "doc_1"], {"doc_0"}, k=1) == 1.0


def test_recall_at_k_miss_in_top_1():
    assert recall_at_k(["doc_1", "doc_0"], {"doc_0"}, k=1) == 0.0


def test_recall_at_k_hit_at_rank_2():
    assert recall_at_k(["doc_1", "doc_0"], {"doc_0"}, k=3) == 1.0


def test_recall_at_k_partial():
    """Two relevant docs, only one in top-3 → 0.5."""
    assert recall_at_k(["a", "x", "y"], {"a", "b"}, k=3) == 0.5


def test_recall_at_k_empty_relevant():
    assert recall_at_k(["a"], set(), k=3) == 0.0


def test_recall_at_k_empty_ranked():
    assert recall_at_k([], {"a"}, k=3) == 0.0


# reciprocal_rank


def test_reciprocal_rank_at_rank_1():
    assert reciprocal_rank(["doc_0"], {"doc_0"}, k=10) == 1.0


def test_reciprocal_rank_at_rank_2():
    assert abs(reciprocal_rank(["x", "doc_0"], {"doc_0"}, k=10) - 0.5) < 1e-9


def test_reciprocal_rank_miss():
    assert reciprocal_rank(["x", "y", "z"], {"doc_0"}, k=10) == 0.0


def test_reciprocal_rank_beyond_k():
    """Relevant doc outside top-k window → 0."""
    ranked = [f"x{i}" for i in range(10)] + ["doc_0"]
    assert reciprocal_rank(ranked, {"doc_0"}, k=10) == 0.0


# ndcg_at_k


def test_ndcg_at_k_perfect():
    """Relevant doc at rank 1 → nDCG = 1.0."""
    assert abs(ndcg_at_k(["doc_0"], {"doc_0"}, k=10) - 1.0) < 1e-9


def test_ndcg_at_k_miss():
    assert ndcg_at_k(["x", "y"], {"doc_0"}, k=10) == 0.0


def test_ndcg_at_k_rank_2_less_than_rank_1():
    ndcg_r1 = ndcg_at_k(["doc_0", "x"], {"doc_0"}, k=10)
    ndcg_r2 = ndcg_at_k(["x", "doc_0"], {"doc_0"}, k=10)
    assert ndcg_r1 > ndcg_r2


# average_precision


def test_ap_single_relevant_rank_1():
    assert abs(average_precision(["doc_0"], {"doc_0"}, k=10) - 1.0) < 1e-9


def test_ap_single_relevant_rank_2():
    """doc at rank 2: precision at hit = 1/2; AP = (1/2) / min(1, k) = 0.5."""
    assert abs(average_precision(["x", "doc_0"], {"doc_0"}, k=10) - 0.5) < 1e-9


def test_ap_no_relevant():
    assert average_precision(["x"], set(), k=10) == 0.0


# rank_metrics


def test_rank_metrics_single_query_perfect():
    rankings = {"q0": ["doc_0", "doc_1"]}
    rels = {"q0": {"doc_0"}}
    m = rank_metrics(rankings, rels)
    assert m["recall@1"] == 1.0
    assert m["mrr@10"] == 1.0


def test_rank_metrics_empty():
    assert rank_metrics({}, {}) == {}


def test_rank_metrics_keys_match_extract_metrics():
    """rank_metrics must emit exactly the same keys as extract_metrics."""
    from scripts.eval_retrieval import extract_metrics  # noqa: F401 — imported for key-shape reference

    rankings = {"q0": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]}
    rels = {"q0": {"a"}}
    m = rank_metrics(rankings, rels)
    expected_keys = {"recall@1", "recall@3", "recall@5", "recall@10", "mrr@10", "ndcg@10", "map@10"}
    assert set(m.keys()) == expected_keys


def test_rank_metrics_averages_across_queries():
    rankings = {"q0": ["doc_0", "x"], "q1": ["x", "doc_1"]}
    rels = {"q0": {"doc_0"}, "q1": {"doc_1"}}
    m = rank_metrics(rankings, rels)
    # q0: mrr=1.0, q1: mrr=0.5 → avg=0.75
    assert abs(m["mrr@10"] - 0.75) < 1e-4


def test_rank_metrics_values_rounded_4dp():
    rankings = {"q0": ["x", "y", "z"]}
    rels = {"q0": {"z"}}
    m = rank_metrics(rankings, rels)
    for k, v in m.items():
        assert v == round(v, 4), f"{k}={v} not rounded to 4dp"


# ---------------------------------------------------------------------------
# run_eval_manual — pure plumbing (mock model, no network)
# ---------------------------------------------------------------------------


def test_run_eval_manual_prefix_none_does_not_prefix(monkeypatch):
    """With prefix_style='none', no query:/passage: prefix should appear in encoded texts."""
    captured: dict = {}

    class FakeModel:
        def encode(self, texts, **kwargs):
            captured["last_texts"] = list(texts)
            import numpy as np

            return np.zeros((len(texts), 4))

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())

    from scripts.eval_retrieval import run_eval_manual

    corpus = {"d0": "Texto."}
    queries = {"q0": "Pergunta?"}
    run_eval_manual("fake-model", corpus, queries, {"q0": {"d0"}}, prefix_style="none", show_progress=False)

    all_texts = captured.get("last_texts", [])
    assert not any(t.startswith("query: ") or t.startswith("passage: ") for t in all_texts)


def test_run_eval_manual_prefix_e5_applies_prefixes(monkeypatch):
    captured: dict = {}

    class FakeModel:
        def encode(self, texts, **kwargs):
            captured.setdefault("calls", []).append(list(texts))
            import numpy as np

            return np.zeros((len(texts), 4))

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())

    from scripts.eval_retrieval import run_eval_manual

    corpus = {"d0": "Texto."}
    queries = {"q0": "Pergunta?"}
    run_eval_manual("fake-model", corpus, queries, {"q0": {"d0"}}, prefix_style="e5", show_progress=False)

    all_texts = [t for call in captured["calls"] for t in call]
    assert any(t.startswith("query: ") for t in all_texts)
    assert any(t.startswith("passage: ") for t in all_texts)


def test_run_eval_manual_invalid_prefix_raises(monkeypatch):
    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: None)
    from scripts.eval_retrieval import run_eval_manual

    with pytest.raises(ValueError, match="prefix_style"):
        run_eval_manual("fake", {}, {}, {}, prefix_style="bert", show_progress=False)


def test_run_eval_manual_score_threshold_drops_hits(monkeypatch):
    """A high score_threshold should result in empty rankings → zero recall."""
    import numpy as np

    class FakeModel:
        call_count = 0

        def encode(self, texts, **kwargs):
            self.call_count += 1
            # First call is corpus (1 doc), second is query (1 query)
            return np.array([[1.0, 0.0, 0.0, 0.0]] * len(texts))

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())

    from scripts.eval_retrieval import run_eval_manual

    corpus = {"d0": "text"}
    queries = {"q0": "query"}
    # cosine(same vec, same vec) = 1.0, but threshold > 1.0 → always empty
    m = run_eval_manual("fake", corpus, queries, {"q0": {"d0"}}, prefix_style="none", score_threshold=1.5, show_progress=False)
    assert m["recall@1"] == 0.0


def test_run_eval_manual_with_identity_reranker(monkeypatch):
    """With IdentityReranker the rankings are the same as dense-only."""
    import numpy as np
    from guardrails.adapters import IdentityReranker

    class FakeModel:
        def encode(self, texts, **kwargs):
            return np.array([[float(i), 0.0, 0.0, 0.0] for i in range(len(texts))])

    monkeypatch.setattr("scripts.eval_retrieval.SentenceTransformer", lambda *a, **kw: FakeModel())

    from scripts.eval_retrieval import run_eval_manual

    corpus = {"d0": "t0", "d1": "t1"}
    queries = {"q0": "q"}
    rels = {"q0": {"d0"}}
    m_plain = run_eval_manual("fake", corpus, queries, rels, prefix_style="none", show_progress=False)
    m_reranked = run_eval_manual("fake", corpus, queries, rels, prefix_style="none", reranker=IdentityReranker(), show_progress=False)
    # IdentityReranker preserves order → same recall
    assert m_plain["recall@1"] == m_reranked["recall@1"]


# ---------------------------------------------------------------------------
# Slow: dense-only manual path must reproduce InformationRetrievalEvaluator
# (anti-tautology gate — building-rigorously §1/§3)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_manual_dense_reproduces_evaluator():
    """Dense-only run_eval_manual on frozen faq_bacen must match InformationRetrievalEvaluator.

    Baseline from models/eval/faq_bacen__*e5-base*.json:
      recall@5 = 0.7480  (±0.005 tolerance)
      mrr@10   = 0.5885  (±0.005)

    If this fails, the manual metric code cannot be trusted for reranker deltas.
    """
    from scripts.eval_retrieval import load_frozen, run_eval_manual

    corpus, queries, relevant_docs = load_frozen("faq_bacen")
    m = run_eval_manual(
        "intfloat/multilingual-e5-base",
        corpus,
        queries,
        relevant_docs,
        prefix_style="e5",
        reranker=None,
        score_threshold=None,
        top_n=len(corpus),  # no truncation — full ranking for recall@10
        show_progress=True,
    )

    tol = 0.005
    assert abs(m["recall@5"] - 0.7480) <= tol, f"recall@5={m['recall@5']:.4f} outside tolerance (expected ~0.7480)"
    assert abs(m["mrr@10"] - 0.5885) <= tol, f"mrr@10={m['mrr@10']:.4f} outside tolerance (expected ~0.5885)"

    # Sanity: recall monotone
    assert m["recall@1"] <= m["recall@3"] <= m["recall@5"] <= m["recall@10"]
