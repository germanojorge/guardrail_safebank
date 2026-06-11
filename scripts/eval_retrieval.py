#!/usr/bin/env python3
"""Retrieval eval harness for the banking RAG pipeline.

Reads frozen JSONL splits (data/eval/), optionally applies E5 prefixes,
runs InformationRetrievalEvaluator, and emits recall@{1,3,5,10}, MRR@10,
nDCG@10, MAP@10 as a markdown table (stdout) + JSON run record.

Usage:
    # Freeze FAQ_BACEN splits from HuggingFace (run once, then commit):
    uv run python scripts/eval_retrieval.py --freeze

    # Eval e5-small baseline on FAQ_BACEN (default, E5 prefixes applied):
    uv run python scripts/eval_retrieval.py

    # Eval a prefix-free model (MiniLM, fine-tune):
    uv run python scripts/eval_retrieval.py --model paraphrase-multilingual-MiniLM-L12-v2 --prefix-style none

    # Eval on banking_kb smoke set (closed-loop, fast):
    uv run python scripts/eval_retrieval.py --dataset banking_kb

    # Eval a different model:
    uv run python scripts/eval_retrieval.py --model intfloat/multilingual-e5-base
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de datasets/transformers

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Ensure scripts/ is importable as a top-level dir regardless of how this
# module is loaded (as __main__, or imported as scripts.eval_retrieval in tests).
sys.path.insert(0, str(Path(__file__).parent))
from _faq_data import load_faq_data as _load_faq_data  # noqa: E402

from sentence_transformers import SentenceTransformer
from sentence_transformers.sentence_transformer.evaluation import InformationRetrievalEvaluator

_DEFAULT_EVAL_MODEL = "intfloat/multilingual-e5-small"


# ---------------------------------------------------------------------------
# Freeze: download FAQ_BACEN → write deterministic JSONL snapshots
# ---------------------------------------------------------------------------


def freeze_faq_bacen(out_dir: str = "data/eval") -> None:
    """Download FAQ_BACEN from HuggingFace and write frozen JSONL splits.

    Rows are sorted by id for byte-reproducibility (D7).
    Safe to re-run — produces identical output given the same upstream data.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    _, corpus, queries, relevant_docs = _load_faq_data()

    # Corpus: sorted by doc_id (lexicographic) for determinism
    corpus_path = Path(out_dir) / "faq_bacen_corpus.jsonl"
    with open(corpus_path, "w", encoding="utf-8") as f:
        for doc_id in sorted(corpus.keys()):
            f.write(json.dumps({"doc_id": doc_id, "text": corpus[doc_id]}, ensure_ascii=False) + "\n")

    # Queries: sorted by numeric suffix of relevant_doc_id (test_N → N) for natural order
    pairs = sorted(zip(queries, relevant_docs), key=lambda qd: int(qd[1].split("_")[1]))
    eval_path = Path(out_dir) / "faq_bacen_eval.jsonl"
    with open(eval_path, "w", encoding="utf-8") as f:
        for i, (q, doc_id) in enumerate(pairs):
            entry = {"query_id": f"q_{i}", "query": q, "relevant_doc_ids": [doc_id]}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Frozen corpus: {len(corpus)} docs → {corpus_path}")
    print(f"Frozen eval:   {len(queries)} queries → {eval_path}")


# ---------------------------------------------------------------------------
# Loader: read frozen JSONL from disk (no network)
# ---------------------------------------------------------------------------


def load_frozen(
    dataset: str,
    data_dir: str = "data/eval",
    kb_dir: str = "data/banking_kb",
) -> tuple[dict[str, str], dict[str, str], dict[str, set[str]]]:
    """Load a frozen eval split from disk.

    Returns:
        corpus: {doc_id: text}
        queries: {query_id: query_text}
        relevant_docs: {query_id: set_of_doc_ids}
    """
    if dataset == "faq_bacen":
        corpus: dict[str, str] = {}
        with open(Path(data_dir) / "faq_bacen_corpus.jsonl", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                corpus[row["doc_id"]] = row["text"]

        queries: dict[str, str] = {}
        relevant_docs: dict[str, set[str]] = {}
        with open(Path(data_dir) / "faq_bacen_eval.jsonl", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                qid = row["query_id"]
                queries[qid] = row["query"]
                relevant_docs[qid] = set(row["relevant_doc_ids"])

        return corpus, queries, relevant_docs

    elif dataset == "banking_kb":
        # Import lazily to avoid pulling QdrantStore/SentenceTransformerProvider at module load
        from ingest_banking_kb import NAMESPACE, _split_paragraphs  # noqa: PLC0415

        corpus = {}
        for path in sorted(Path(kb_dir).glob("*.md")):
            content = path.read_text(encoding="utf-8")
            for idx, para in enumerate(_split_paragraphs(content)):
                doc_id = str(uuid.uuid5(NAMESPACE, f"{path.name}:{idx}"))
                corpus[doc_id] = para

        queries = {}
        relevant_docs = {}
        eval_path = Path(data_dir) / "banking_kb_eval.jsonl"
        with open(eval_path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                row = json.loads(stripped)
                qid = row["query_id"]
                queries[qid] = row["query"]
                relevant_docs[qid] = set(row["relevant_doc_ids"])

        return corpus, queries, relevant_docs

    else:
        raise ValueError(f"Unknown dataset: {dataset!r}. Choose 'faq_bacen' or 'banking_kb'.")


# ---------------------------------------------------------------------------
# Eval: optionally apply E5 prefixes + run InformationRetrievalEvaluator
# ---------------------------------------------------------------------------

_VALID_PREFIX_STYLES = {"e5", "none"}


def apply_prefixes(texts: dict[str, str], role: str, style: str) -> dict[str, str]:
    """Conditionally prepend E5 role prefix to each text in a dict.

    Args:
        texts: {id: text}
        role: "query" or "passage" (used only when style == "e5")
        style: "e5" applies "<role>: " prefix; "none" returns texts unchanged.
    """
    if style == "e5":
        return {k: f"{role}: {v}" for k, v in texts.items()}
    return dict(texts)


def run_eval(
    model_name: str,
    corpus: dict[str, str],
    queries: dict[str, str],
    relevant_docs: dict[str, set[str]],
    name: str,
    prefix_style: str = "e5",
) -> dict[str, float]:
    """Run IR eval with optional E5 prefixes (mirrors embedding.py:63-71).

    Args:
        prefix_style: "e5" applies query:/passage: prefixes (correct for E5 models);
            "none" passes texts unmodified (correct for MiniLM and fine-tuned BERT models
            whose config_sentence_transformers.json has empty prompts). Raises ValueError
            for any other value.

    Note:
        E5-vs-MiniLM is not perfectly apples-to-apples (different pretraining recipes).
        The fine-tune was trained on FAQ_BACEN train split — strong FAQ_BACEN scores may
        be train-distribution overfit; always gate with banking_kb anti-regression (SCRUM-38).
    """
    if prefix_style not in _VALID_PREFIX_STYLES:
        raise ValueError(f"prefix_style must be one of {_VALID_PREFIX_STYLES!r}, got {prefix_style!r}")

    eval_corpus = apply_prefixes(corpus, "passage", prefix_style)
    eval_queries = apply_prefixes(queries, "query", prefix_style)

    model = SentenceTransformer(model_name, device="cpu")

    ev = InformationRetrievalEvaluator(
        queries=eval_queries,
        corpus=eval_corpus,
        relevant_docs=relevant_docs,
        name=name,
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[1, 3, 5, 10],
        mrr_at_k=[10],
        ndcg_at_k=[10],
        map_at_k=[10],
        show_progress_bar=True,
    )
    return ev(model)


def measure_latency_ms_per_query(
    model_name: str,
    queries: dict[str, str],
    prefix_style: str = "e5",
    warmup: int = 3,
) -> float:
    """Measure mean CPU encode latency in ms per single query.

    Warms up the model first (first encode triggers JIT / weight load), then
    times single-query encodes over all eval queries and returns the mean ms.

    Uses batch_size=1 + normalize_embeddings=True to mirror production
    embed_queries (embedding.py:55-71). Latency numbers are indicative and
    machine-dependent — treat as relative, not absolute benchmarks.
    """
    if prefix_style not in _VALID_PREFIX_STYLES:
        raise ValueError(f"prefix_style must be one of {_VALID_PREFIX_STYLES!r}, got {prefix_style!r}")

    model = SentenceTransformer(model_name, device="cpu")
    query_list = list(queries.values())

    prefix = "query: " if prefix_style == "e5" else ""

    # Warm-up passes — discard
    for q in (query_list * warmup)[:warmup]:
        model.encode([prefix + q], batch_size=1, normalize_embeddings=True)

    # Timed passes — one query at a time
    times: list[float] = []
    for q in query_list:
        t0 = time.perf_counter()
        model.encode([prefix + q], batch_size=1, normalize_embeddings=True)
        times.append((time.perf_counter() - t0) * 1000.0)

    return round(sum(times) / len(times), 3)


# ---------------------------------------------------------------------------
# Metrics: extract, serialize, render
# ---------------------------------------------------------------------------


def extract_metrics(results: dict[str, float], name: str) -> dict[str, float]:
    """Extract key metrics from InformationRetrievalEvaluator output dict."""
    metrics: dict[str, float] = {}
    for k in [1, 3, 5, 10]:
        key = f"{name}_cosine_recall@{k}"
        if key in results:
            metrics[f"recall@{k}"] = round(results[key], 4)
    for metric_name, suffix in [("mrr@10", "mrr@10"), ("ndcg@10", "ndcg@10"), ("map@10", "map@10")]:
        key = f"{name}_cosine_{suffix}"
        if key in results:
            metrics[metric_name] = round(results[key], 4)
    return metrics


def write_run_json(out_dir: str, payload: dict) -> Path:
    """Write run metadata + metrics to a timestamped JSON file."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    model_slug = payload["model"].replace("/", "__")
    ts = payload["timestamp"][:19].replace(":", "").replace("-", "").replace("T", "_")
    fname = f"{payload['dataset']}__{model_slug}__{ts}.json"
    out_path = Path(out_dir) / fname
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def render_markdown(metrics: dict[str, float]) -> str:
    """Render metrics dict as a markdown table."""
    rows = [f"| {k} | {v:.4f} |" for k, v in sorted(metrics.items())]
    return "\n".join(["| Metric | Score |", "|--------|-------|", *rows])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=("Eval retrieval metrics for the banking RAG pipeline. Emits recall@{1,3,5,10}, MRR@10, nDCG@10, MAP@10."))
    parser.add_argument(
        "--model",
        default=_DEFAULT_EVAL_MODEL,
        help=f"HuggingFace model id (default: {_DEFAULT_EVAL_MODEL})",
    )
    parser.add_argument(
        "--dataset",
        default="faq_bacen",
        choices=["faq_bacen", "banking_kb"],
        help="Which frozen split to evaluate (default: faq_bacen)",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Regenerate frozen JSONL from FAQ_BACEN HF dataset and exit (requires network)",
    )
    parser.add_argument(
        "--out-dir",
        default="models/eval",
        help="Where to write run JSON (default: models/eval)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/eval",
        help="Where frozen JSONL lives (default: data/eval)",
    )
    parser.add_argument(
        "--prefix-style",
        default="e5",
        choices=["e5", "none"],
        dest="prefix_style",
        help="Prefix strategy: 'e5' applies query:/passage: (default); 'none' for MiniLM/fine-tuned BERT",
    )
    # Reserved for SCRUM-39 — not yet implemented
    parser.add_argument("--reranker", help=argparse.SUPPRESS)
    parser.add_argument("--threshold", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--hybrid", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.freeze:
        freeze_faq_bacen(args.data_dir)
        return 0

    print(f"Loading frozen split: {args.dataset} ...")
    corpus, queries, relevant_docs = load_frozen(args.dataset, args.data_dir)
    print(f"Corpus: {len(corpus)}  Queries: {len(queries)}")

    print(f"\nRunning eval — model: {args.model}  prefix_style: {args.prefix_style} ...")
    results = run_eval(args.model, corpus, queries, relevant_docs, name=args.dataset, prefix_style=args.prefix_style)

    metrics = extract_metrics(results, args.dataset)

    print("\nMeasuring latency ...")
    latency = measure_latency_ms_per_query(args.model, queries, prefix_style=args.prefix_style)

    closed_loop = args.dataset == "banking_kb"
    payload = {
        "model": args.model,
        "dataset": args.dataset,
        "prefix_style": args.prefix_style,
        "prefixes_applied": args.prefix_style == "e5",
        "closed_loop": closed_loop,
        "n_queries": len(queries),
        "n_corpus": len(corpus),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "seed": 42,
        "latency_ms_per_query": latency,
        "metrics": metrics,
    }

    out_path = write_run_json(args.out_dir, payload)
    print(f"\nRun saved: {out_path}")
    print("\n" + render_markdown(metrics))

    if closed_loop:
        print("\nWARNING: banking_kb is a closed-loop eval set — queries hand-crafted from same corpus.")
        print("  Numbers confirm plumbing only, NOT generalizable retrieval quality.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
