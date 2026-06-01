"""
One-shot local script to pre-screen RealToxicityPrompts candidates for toxic fixture selection.
NOT run in CI. Run manually before updating tests/adversarial/fixtures/toxic_external.jsonl:

    uv run python scripts/screen_realtoxicityprompts.py | tee /tmp/rtp_screen.txt

Downloads the "challenging" split from allenai/real-toxicity-prompts (CC-BY 4.0),
scores each prompt through Detoxify("multilingual"), and prints the top-20 candidates
with max_subscore > 0.75 (margin above the 0.7 production threshold).

Per building-rigorously.md §1: do NOT lower the threshold if fewer than 15 candidates
pass — stop and re-check the model name or dataset.
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de importar datasets/transformers

from detoxify import Detoxify

RTP_SUBSET_SIZE = 200
SCORE_THRESHOLD = 0.75
CATEGORIES = ("toxicity", "severe_toxicity", "obscene", "threat", "insult")


def main() -> None:
    print("Loading RealToxicityPrompts (challenging split) from HF datasets ...")
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' package not found. Install with: uv add --dev datasets")
        raise SystemExit(1)

    ds = load_dataset("allenai/real-toxicity-prompts", split="challenging", trust_remote_code=True)
    print(f"Dataset loaded: {len(ds)} rows")

    print("Loading Detoxify(multilingual) ...")
    model = Detoxify("multilingual")

    candidates: list[tuple[int, float, str, dict[str, float]]] = []
    for i, row in enumerate(ds):
        if i >= RTP_SUBSET_SIZE:
            break
        prompt_text = str(row.get("prompt", {}).get("text", ""))
        if not prompt_text.strip():
            continue
        scores = model.predict(prompt_text)
        subscores = {k: float(scores[k]) for k in CATEGORIES}
        max_score = max(subscores.values())
        if max_score > SCORE_THRESHOLD:
            candidates.append((i, max_score, prompt_text, subscores))

    candidates.sort(key=lambda x: -x[1])
    print(f"\n=== {len(candidates)} candidates above threshold {SCORE_THRESHOLD} (out of first {RTP_SUBSET_SIZE} rows) ===\n")
    for idx, max_score, text, subscores in candidates[:20]:
        print(f"idx={idx}  max_score={max_score:.4f}")
        print(f"  subscores={subscores}")
        print(f"  text={text[:150]!r}")
        print()

    if len(candidates) < 15:
        print("WARNING: fewer than 15 candidates cleared the bar — do NOT lower threshold.")
        print("Re-check model name or dataset split.")


if __name__ == "__main__":
    main()
