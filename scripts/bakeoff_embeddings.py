#!/usr/bin/env python3
"""Embedding model bake-off driver (SCRUM-38).

Runs the retrieval harness across 4 models on the same frozen split, captures
per-query CPU latency, and emits an F-2 comparison table (stdout + markdown).

Usage:
    # Full bake-off on FAQ_BACEN (downloads models on first run, slow):
    uv run python scripts/bakeoff_embeddings.py

    # Anti-regression gate: run winner + e5-small on banking_kb before shipping:
    uv run python scripts/bakeoff_embeddings.py --dataset banking_kb

    # Specify output directory:
    uv run python scripts/bakeoff_embeddings.py --out-dir models/eval
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF — DEVE vir antes de sentence_transformers

import argparse
import json
from datetime import datetime
from pathlib import Path

from eval_retrieval import (
    extract_metrics,
    load_frozen,
    measure_latency_ms_per_query,
    run_eval,
    write_run_json,
)

# ---------------------------------------------------------------------------
# Model matrix — per-model prefix_style is CRITICAL for fair comparison
# (see plan SCRUM-38: E5 prefixes on MiniLM/fine-tune handicap them unfairly)
# ---------------------------------------------------------------------------

MODELS = [
    {
        "model_id": "intfloat/multilingual-e5-small",
        "dim": 384,
        "prefix_style": "e5",
        "label": "e5-small (current)",
    },
    {
        "model_id": "intfloat/multilingual-e5-base",
        "dim": 768,
        "prefix_style": "e5",
        "label": "e5-base",
    },
    {
        "model_id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "dim": 384,
        "prefix_style": "none",
        "label": "MiniLM-L12-v2",
    },
    {
        "model_id": "models/itau-embedding-finetuned",
        "dim": 384,
        "prefix_style": "none",
        "label": "itau-finetuned (local)",
    },
]


def render_bakeoff_table(rows: list[dict]) -> str:
    """Render the F-2 comparison table as markdown."""
    header = "| Model | dim | prefix_style | recall@5 | MRR@10 | nDCG@10 | latency_ms/q |"
    sep = "|-------|-----|--------------|----------|--------|---------|--------------|"
    lines = [header, sep]
    for r in rows:
        m = r["metrics"]
        lines.append(
            f"| {r['label']} | {r['dim']} | {r['prefix_style']} | {m.get('recall@5', float('nan')):.4f} | {m.get('mrr@10', float('nan')):.4f} | {m.get('ndcg@10', float('nan')):.4f} | {r['latency_ms_per_query']:.1f} |"
        )
    return "\n".join(lines)


def pick_winner(rows: list[dict]) -> dict:
    """Return the row with highest recall@5, tie-broken by mrr@10."""
    return max(rows, key=lambda r: (r["metrics"].get("recall@5", 0.0), r["metrics"].get("mrr@10", 0.0)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Embedding model bake-off across 4 models on a frozen eval split.")
    parser.add_argument(
        "--dataset",
        default="faq_bacen",
        choices=["faq_bacen", "banking_kb"],
        help="Which frozen split to evaluate (default: faq_bacen)",
    )
    parser.add_argument(
        "--out-dir",
        default="models/eval",
        help="Where to write run JSONs and the markdown table (default: models/eval)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/eval",
        help="Where frozen JSONL lives (default: data/eval)",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip models whose local path does not exist (useful for banking_kb anti-regression with fewer models)",
    )
    args = parser.parse_args()

    print(f"Loading frozen split: {args.dataset} ...")
    corpus, queries, relevant_docs = load_frozen(args.dataset, args.data_dir)
    print(f"Corpus: {len(corpus)}  Queries: {len(queries)}\n")

    rows: list[dict] = []

    for spec in MODELS:
        model_id = spec["model_id"]
        label = spec["label"]
        prefix_style = spec["prefix_style"]
        dim = spec["dim"]

        # Skip local models that don't exist yet (e.g. fine-tune not trained)
        if model_id.startswith("models/") and not Path(model_id).exists():
            if args.skip_missing:
                print(f"SKIP {label} — path {model_id!r} not found (--skip-missing)\n")
                continue
            else:
                print(f"WARNING: {label} — path {model_id!r} not found, skipping\n")
                continue

        print(f"[{label}] Running eval  prefix_style={prefix_style!r} ...")
        try:
            results = run_eval(model_id, corpus, queries, relevant_docs, name=args.dataset, prefix_style=prefix_style)
            metrics = extract_metrics(results, args.dataset)
        except Exception as exc:
            print(f"  ERROR during eval: {exc}")
            continue

        print(f"[{label}] Measuring latency ...")
        try:
            latency = measure_latency_ms_per_query(model_id, queries, prefix_style=prefix_style)
        except Exception as exc:
            print(f"  ERROR during latency: {exc}")
            latency = float("nan")

        row = {
            "label": label,
            "model_id": model_id,
            "dim": dim,
            "prefix_style": prefix_style,
            "latency_ms_per_query": latency,
            "metrics": metrics,
        }
        rows.append(row)

        payload = {
            "model": model_id,
            "dataset": args.dataset,
            "prefix_style": prefix_style,
            "prefixes_applied": prefix_style == "e5",
            "closed_loop": args.dataset == "banking_kb",
            "n_queries": len(queries),
            "n_corpus": len(corpus),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "seed": 42,
            "latency_ms_per_query": latency,
            # Honesty note: latency is indicative CPU latency on the run machine,
            # not a benchmark guarantee. E5-vs-MiniLM comparison is not perfectly
            # apples-to-apples (different pretraining). Fine-tune score on FAQ_BACEN
            # may reflect train-distribution overfit — gate with banking_kb.
            "metrics": metrics,
        }
        out_path = write_run_json(args.out_dir, payload)
        print(f"  saved: {out_path}\n")

    if not rows:
        print("No models evaluated — nothing to report.")
        return 1

    table_md = render_bakeoff_table(rows)
    print("\n=== Bake-off Results ===\n")
    print(table_md)

    # Write the committed F-2 artifact
    if args.dataset == "faq_bacen":
        artifact_path = Path(args.out_dir) / "bakeoff_faq_bacen.md"
    else:
        artifact_path = Path(args.out_dir) / f"bakeoff_{args.dataset}.md"

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        f"# Embedding Model Bake-off — {args.dataset}\n\n"
        f"Generated: {datetime.utcnow().isoformat()}Z\n\n"
        f"**Caveat:** E5-vs-MiniLM comparison is not perfectly apples-to-apples "
        f"(different pretraining recipes). The fine-tune was trained on FAQ_BACEN "
        f"train split — a strong FAQ_BACEN score may reflect train-distribution overfit. "
        f"Gate with `banking_kb` anti-regression before shipping any model change.\n\n"
        f"Latency numbers are indicative CPU latency on the run machine, not a benchmark guarantee.\n\n" + table_md + "\n",
        encoding="utf-8",
    )
    print(f"\nArtifact written: {artifact_path}")

    winner = pick_winner(rows)
    print("\n=== Winner suggestion (highest recall@5, tie-break MRR@10) ===")
    print(f"  {winner['label']}  recall@5={winner['metrics'].get('recall@5', 'N/A')}  mrr@10={winner['metrics'].get('mrr@10', 'N/A')}")
    print("\nNOTE: Do NOT update config.yaml until banking_kb anti-regression gate passes.")
    print("      Run: uv run python scripts/bakeoff_embeddings.py --dataset banking_kb")

    # Serialize rows summary to JSON for programmatic consumption
    summary_path = Path(args.out_dir) / f"bakeoff_{args.dataset}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "dataset": args.dataset,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "rows": [
                    {
                        "model_id": r["model_id"],
                        "label": r["label"],
                        "dim": r["dim"],
                        "prefix_style": r["prefix_style"],
                        "latency_ms_per_query": r["latency_ms_per_query"],
                        "metrics": r["metrics"],
                    }
                    for r in rows
                ],
                "winner": winner["model_id"],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Summary JSON: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
