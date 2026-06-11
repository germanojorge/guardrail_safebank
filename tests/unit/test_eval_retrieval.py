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
