"""
One-shot local script to pre-screen HateBR candidates for toxic fixture selection.

NOT run in CI. Run manually before updating tests/fixtures/hatebr_samples.py:
    uv run python scripts/screen_hatebr.py | tee /tmp/hatebr_screen.txt

Downloads HateBR.csv from GitHub (raw URL), filters hate speech rows
(label_final == 1, binary label in HateBR v1.0), scores each through
Detoxify("multilingual"), and prints candidates with max_subscore > 0.75
(margin above the 0.7 threshold).

Note: HateBR v1.0 columns are id, comentario, anotator1-3, label_final, links_post,
account_post. The plan originally referenced offensiveness_levels==3 (a v2 schema
that doesn't exist in the committed dataset) — corrected during execution 2026-05-26.

Per building-rigorously.md §1: do NOT lower the threshold if <3 candidates pass —
stop and re-check the model name or download.
"""

import csv
import io
import urllib.request

from detoxify import Detoxify

HATEBR_URL = (
    "https://raw.githubusercontent.com/franciellevargas/HateBR/main/dataset/HateBR.csv"
)
SCORE_THRESHOLD = 0.75
CATEGORIES = ("toxicity", "severe_toxicity", "obscene", "threat", "insult")


def main() -> None:
    print(f"Downloading HateBR from {HATEBR_URL} ...")
    with urllib.request.urlopen(HATEBR_URL) as resp:
        raw = resp.read().decode("utf-8")

    print("Loading Detoxify(multilingual) ...")
    model = Detoxify("multilingual")

    reader = csv.DictReader(io.StringIO(raw))
    candidates = []
    for i, row in enumerate(reader):
        if row.get("label_final", "").strip() != "1":
            continue
        text = row.get("comentario", "").strip()
        if not text:
            continue
        scores = model.predict(text)
        subscores = {k: float(scores[k]) for k in CATEGORIES}
        max_score = max(subscores.values())
        if max_score > SCORE_THRESHOLD:
            row_id = row.get("id", "").strip() or str(i)
            candidates.append((row_id, max_score, text, subscores))

    candidates.sort(key=lambda x: -x[1])
    print(f"\n=== {len(candidates)} candidates above threshold {SCORE_THRESHOLD} ===\n")
    for row_id, max_score, text, subscores in candidates[:8]:
        print(f"row_id={row_id}  max_score={max_score:.4f}")
        print(f"  subscores={subscores}")
        print(f"  text={text[:120]!r}")
        print()

    if len(candidates) < 3:
        print(
            "WARNING: fewer than 3 candidates cleared the bar — do NOT lower threshold."
        )
        print("Re-check model name or dataset download.")


if __name__ == "__main__":
    main()
