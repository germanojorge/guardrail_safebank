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
# Pure IR metric helpers (manual retrieval path — required for reranker eval)
# ---------------------------------------------------------------------------
# These are independent of any model; unit-testable with no network.
# Shape mirrors extract_metrics: recall@{1,3,5,10}, mrr@10, ndcg@10, map@10.
# ---------------------------------------------------------------------------


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Proportion of relevant docs found in the top-k ranked list."""
    if not relevant:
        return 0.0
    hits = sum(1 for doc in ranked[:k] if doc in relevant)
    return hits / min(len(relevant), k)


def reciprocal_rank(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    """1/rank of the first relevant document within top-k, else 0."""
    for i, doc in enumerate(ranked[:k]):
        if doc in relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    """nDCG@k with binary relevance.

    DCG = sum(1/log2(rank+1)) for relevant docs in top-k.
    IDCG = ideal DCG (all relevant docs at the top).
    """
    import math

    dcg = sum(1.0 / math.log2(i + 2) for i, doc in enumerate(ranked[:k]) if doc in relevant)
    n_ideal = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_ideal))
    return dcg / idcg if idcg > 0 else 0.0


def average_precision(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    """Average Precision at k (AP@k) with binary relevance."""
    if not relevant:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for i, doc in enumerate(ranked[:k]):
        if doc in relevant:
            hits += 1
            precision_sum += hits / (i + 1)
    return precision_sum / min(len(relevant), k)


def rank_metrics(
    per_query_rankings: dict[str, list[str]],
    relevant_docs: dict[str, set[str]],
) -> dict[str, float]:
    """Aggregate IR metrics across all queries.

    Args:
        per_query_rankings: {query_id: [doc_id_rank1, doc_id_rank2, ...]}
        relevant_docs: {query_id: set_of_relevant_doc_ids}

    Returns:
        Dict with keys recall@{1,3,5,10}, mrr@10, ndcg@10, map@10 — rounded 4dp.
        Same key names as extract_metrics for interchangeability.
    """
    n = len(per_query_rankings)
    if n == 0:
        return {}

    recalls: dict[int, float] = {k: 0.0 for k in [1, 3, 5, 10]}
    mrr = 0.0
    ndcg = 0.0
    ap = 0.0

    for qid, ranked in per_query_rankings.items():
        rel = relevant_docs.get(qid, set())
        for k in [1, 3, 5, 10]:
            recalls[k] += recall_at_k(ranked, rel, k)
        mrr += reciprocal_rank(ranked, rel, k=10)
        ndcg += ndcg_at_k(ranked, rel, k=10)
        ap += average_precision(ranked, rel, k=10)

    return {
        "recall@1": round(recalls[1] / n, 4),
        "recall@3": round(recalls[3] / n, 4),
        "recall@5": round(recalls[5] / n, 4),
        "recall@10": round(recalls[10] / n, 4),
        "mrr@10": round(mrr / n, 4),
        "ndcg@10": round(ndcg / n, 4),
        "map@10": round(ap / n, 4),
    }


# ---------------------------------------------------------------------------
# Manual retrieval path: embed → (threshold) → (rerank) → metrics
# ---------------------------------------------------------------------------
# Required for cross-encoder eval since InformationRetrievalEvaluator only
# supports bi-encoder scoring.  The dense-only path must reproduce
# InformationRetrievalEvaluator numbers — that's the anti-tautology check
# (building-rigorously §1/§3; see test_eval_retrieval.py::test_manual_dense_reproduces_evaluator).
# ---------------------------------------------------------------------------


def run_eval_manual(
    model_name: str,
    corpus: dict[str, str],
    queries: dict[str, str],
    relevant_docs: dict[str, set[str]],
    *,
    prefix_style: str = "e5",
    reranker=None,
    score_threshold: float | None = None,
    top_n: int = 20,
    final_top_k: int = 3,
    show_progress: bool = True,
) -> dict[str, float]:
    """Manual embed → (threshold) → (rerank) → metrics path.

    Unlike run_eval (which delegates entirely to InformationRetrievalEvaluator
    and cannot accommodate a cross-encoder), this function explicitly computes
    cosine scores, applies an optional threshold, optionally reranks, then
    calls rank_metrics on the resulting ordered lists.

    The reranker receives raw query/passage text without E5 prefixes —
    cross-encoders read plain text (plan D4).

    To compute recall@{1,3,5,10} correctly the full reranked list (up to
    top_n candidates) is passed to rank_metrics, not just the final_top_k
    production slice.  For production node wiring the final_top_k=3 slice
    is done inside nodes.py::retrieve.

    Args:
        model_name: HF bi-encoder model id.
        corpus: {doc_id: text}
        queries: {query_id: text}
        relevant_docs: {query_id: set_of_doc_ids}
        prefix_style: "e5" or "none" — applied to bi-encoder inputs only.
        reranker: Optional object implementing rerank(query, hits, top_k).
        score_threshold: Drop dense hits with cosine score < threshold.
        top_n: Dense candidate count (then filter/rerank).
        final_top_k: After reranking, slice this many for rank_metrics.
            Use top_n to compute full recall@10; use 3 to mirror production.
        show_progress: Show tqdm progress bars during encoding.

    Returns:
        Dict of recall@{1,3,5,10}, mrr@10, ndcg@10, map@10.
    """
    import numpy as np

    from guardrails.adapters.vector_store import SearchHit

    if prefix_style not in _VALID_PREFIX_STYLES:
        raise ValueError(f"prefix_style must be one of {_VALID_PREFIX_STYLES!r}, got {prefix_style!r}")

    model = SentenceTransformer(model_name, device="cpu")

    corpus_ids = list(corpus.keys())
    corpus_texts_raw = [corpus[did] for did in corpus_ids]
    corpus_texts = [f"passage: {t}" for t in corpus_texts_raw] if prefix_style == "e5" else corpus_texts_raw

    if show_progress:
        print(f"  Encoding {len(corpus_ids)} corpus docs ...")
    corpus_vecs: np.ndarray = model.encode(corpus_texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=show_progress)

    query_ids = list(queries.keys())
    query_texts_raw = [queries[qid] for qid in query_ids]
    query_texts = [f"query: {t}" for t in query_texts_raw] if prefix_style == "e5" else query_texts_raw

    if show_progress:
        print(f"  Encoding {len(query_ids)} queries ...")
    query_vecs: np.ndarray = model.encode(query_texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=show_progress)

    per_query_rankings: dict[str, list[str]] = {}

    for q_idx, qid in enumerate(query_ids):
        qvec = query_vecs[q_idx]

        # Cosine scores: normalized embeddings → dot product == cosine
        scores: np.ndarray = corpus_vecs @ qvec

        # Top-N dense candidates
        top_indices = scores.argsort()[::-1][:top_n]
        hits = [SearchHit(id=corpus_ids[i], score=float(scores[i]), text=corpus_texts_raw[i]) for i in top_indices]

        # Optional cosine threshold (applied before reranker — plan D4)
        if score_threshold is not None:
            hits = [h for h in hits if h.score >= score_threshold]

        # Optional cross-encoder reranker (plain text — no E5 prefix)
        if reranker is not None and hits:
            # Request all surviving hits so rank_metrics can compute recall@10
            hits = reranker.rerank(query_texts_raw[q_idx], hits, top_k=len(hits))
        else:
            # No reranker: rank by cosine, slice to final_top_k for the ranking
            hits = hits[:final_top_k]

        per_query_rankings[qid] = [str(h.id) for h in hits]

    return rank_metrics(per_query_rankings, relevant_docs)


# ---------------------------------------------------------------------------
# Threshold sweep: on-topic recall retention vs off-topic rejection
# ---------------------------------------------------------------------------


def threshold_sweep(
    model_name: str,
    corpus: dict[str, str],
    queries: dict[str, str],
    relevant_docs: dict[str, set[str]],
    prefix_style: str = "e5",
    thresholds: list[float] | None = None,
    top_n: int = 20,
) -> list[dict]:
    """Sweep cosine thresholds, measuring recall@3 retention and off-topic rejection.

    Off-topic queries come from _DEFAULT_OUT_OF_SCOPE (guardrails/validators/out_of_scope.py)
    — a different source from the corpus (building-rigorously §1, D2).
    Queries that return ≥1 hit above threshold are "not rejected".

    Args:
        thresholds: list of cosine values to sweep. Defaults to 0.70..0.92 step 0.02.

    Returns:
        List of dicts with keys: threshold, recall@3, offtopic_rejection_pct.
    """
    import numpy as np

    # Off-topic seeds from a different source (anti-loop-closed, D2)
    from guardrails.validators.out_of_scope import _DEFAULT_OUT_OF_SCOPE as _out_of_scope_seeds

    if thresholds is None:
        thresholds = [round(0.70 + i * 0.02, 2) for i in range(12)]  # 0.70 … 0.92

    model = SentenceTransformer(model_name, device="cpu")

    corpus_ids = list(corpus.keys())
    corpus_texts_raw = [corpus[did] for did in corpus_ids]
    corpus_texts = [f"passage: {t}" for t in corpus_texts_raw] if prefix_style == "e5" else corpus_texts_raw

    print(f"  Encoding {len(corpus_ids)} corpus docs for sweep ...")
    corpus_vecs: np.ndarray = model.encode(corpus_texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)

    # Encode on-topic queries
    query_ids = list(queries.keys())
    query_texts_raw = [queries[qid] for qid in query_ids]
    query_texts = [f"query: {t}" for t in query_texts_raw] if prefix_style == "e5" else query_texts_raw
    print(f"  Encoding {len(query_ids)} on-topic queries ...")
    query_vecs: np.ndarray = model.encode(query_texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)

    # Encode off-topic seeds
    offtopic_texts = [f"query: {t}" for t in _out_of_scope_seeds] if prefix_style == "e5" else list(_out_of_scope_seeds)
    print(f"  Encoding {len(offtopic_texts)} off-topic seeds ...")
    offtopic_vecs: np.ndarray = model.encode(offtopic_texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)

    # Precompute all query-corpus scores
    all_on_scores: np.ndarray = query_vecs @ corpus_vecs.T  # (n_queries, n_corpus)
    all_off_scores: np.ndarray = offtopic_vecs @ corpus_vecs.T  # (n_seeds, n_corpus)

    rows = []
    for thr in thresholds:
        # On-topic: compute recall@3 after threshold filtering
        per_query_rankings: dict[str, list[str]] = {}
        for q_idx, qid in enumerate(query_ids):
            scores = all_on_scores[q_idx]
            top_indices = scores.argsort()[::-1][:top_n]
            hits = [corpus_ids[i] for i in top_indices if scores[i] >= thr]
            per_query_rankings[qid] = hits[:3]
        on_metrics = rank_metrics(per_query_rankings, relevant_docs)
        recall3 = on_metrics.get("recall@3", 0.0)

        # Off-topic: fraction that return NO hit above threshold = rejection rate
        rejected = sum(1 for i in range(len(_out_of_scope_seeds)) if all_off_scores[i].max() < thr)
        rejection_pct = round(rejected / len(_out_of_scope_seeds) * 100, 1)

        rows.append({"threshold": thr, "recall@3": recall3, "offtopic_rejection_pct": rejection_pct})

    return rows


def render_sweep_table(rows: list[dict]) -> str:
    """Render threshold-sweep rows as a markdown table."""
    header = "| threshold | recall@3 | off-topic rejection % |"
    sep = "|-----------|----------|----------------------|"
    lines = [header, sep]
    for r in rows:
        lines.append(f"| {r['threshold']:.2f} | {r['recall@3']:.4f} | {r['offtopic_rejection_pct']:.1f}% |")
    return "\n".join(lines)


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
    parser.add_argument(
        "--reranker",
        default=None,
        help="HF cross-encoder model id to rerank dense candidates (e.g. cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        dest="top_n",
        help="Dense candidate count before reranking (default: 20; only used with --reranker)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Minimum cosine score to retain a dense hit (default: None = no filtering)",
    )
    parser.add_argument(
        "--threshold-sweep",
        action="store_true",
        dest="threshold_sweep",
        help="Sweep cosine thresholds and report recall@3 retention + off-topic rejection %%",
    )
    # Hybrid BM25+dense: deferred to post-MVP (SCRUM-39 talking point)
    parser.add_argument("--hybrid", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.freeze:
        freeze_faq_bacen(args.data_dir)
        return 0

    print(f"Loading frozen split: {args.dataset} ...")
    corpus, queries, relevant_docs = load_frozen(args.dataset, args.data_dir)
    print(f"Corpus: {len(corpus)}  Queries: {len(queries)}")

    if args.threshold_sweep:
        print(f"\nRunning threshold sweep — model: {args.model}  prefix_style: {args.prefix_style} ...")
        rows = threshold_sweep(args.model, corpus, queries, relevant_docs, prefix_style=args.prefix_style, top_n=args.top_n)
        print("\n" + render_sweep_table(rows))
        return 0

    use_manual = args.reranker is not None or args.threshold is not None
    if use_manual:
        reranker = None
        if args.reranker:
            from guardrails.adapters.reranker import CrossEncoderReranker

            print(f"  Loading reranker: {args.reranker} ...")
            reranker = CrossEncoderReranker(model_name=args.reranker)

        print(f"\nRunning manual eval — model: {args.model}  reranker: {args.reranker}  threshold: {args.threshold}  top_n: {args.top_n} ...")
        metrics = run_eval_manual(
            args.model,
            corpus,
            queries,
            relevant_docs,
            prefix_style=args.prefix_style,
            reranker=reranker,
            score_threshold=args.threshold,
            top_n=args.top_n,
        )
        latency = 0.0  # reranker latency measured separately in production diagnostics
    else:
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
        "reranker": args.reranker,
        "score_threshold": args.threshold,
        "top_n": args.top_n,
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
