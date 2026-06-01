#!/usr/bin/env python3
"""Build semantic jailbreak index for JailbreakValidator L1c.

Downloads the Necent jailbreak dataset, filters for adversarial prompts,
deduplicates, embeds with paraphrase-multilingual-MiniLM-L12-v2, and saves
to data/jailbreak_index.npz.

Requires Hugging Face login if dataset is gated:
    huggingface-cli login

Fallback: if Necent dataset is unavailable, uses the open-source
Octavio-Santana/prompt-injection-attack-detection-multilingual dataset.
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de importar datasets/transformers

import hashlib
import os
import sys

import numpy as np


def normalize(text: str) -> str:
    return text.strip().lower()


def md5(text: str) -> str:
    return hashlib.md5(normalize(text).encode("utf-8")).hexdigest()


def load_necent() -> list[str]:
    print("Loading Necent/llm-jailbreak-prompt-injection-dataset ...")
    from datasets import load_dataset

    ds = load_dataset("Necent/llm-jailbreak-prompt-injection-dataset", split="train")
    texts = []
    for row in ds:
        if row.get("prompt_adversarial", 0) != 1:
            continue
        language = row.get("language", "")
        if language not in {"pt", "pt-BR", "en", "es"}:
            continue
        prompt = row.get("prompt", "").strip()
        if prompt:
            texts.append(prompt)
    return texts


def load_fallback() -> list[str]:
    print("Loading Octavio-Santana/prompt-injection-attack-detection-multilingual (fallback) ...")
    from datasets import load_dataset

    ds = load_dataset("Octavio-Santana/prompt-injection-attack-detection-multilingual", split="train")
    texts = []
    for row in ds:
        prompt = row.get("text", "").strip()
        if prompt:
            texts.append(prompt)
    return texts


def build_index(
    texts: list[str],
    output_path: str = "data/jailbreak_index.npz",
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
) -> None:
    from sentence_transformers import SentenceTransformer

    seen: set[str] = set()
    unique_texts: list[str] = []
    for t in texts:
        h = md5(t)
        if h not in seen:
            seen.add(h)
            unique_texts.append(t)

    print(f"Total texts: {len(texts)}, after dedup: {len(unique_texts)}")

    model = SentenceTransformer(model_name)
    embeddings = model.encode(unique_texts, normalize_embeddings=True, show_progress_bar=True)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    np.savez_compressed(output_path, texts=np.array(unique_texts), embeddings=embeddings)

    lang_counts: dict[str, int] = {}
    for t in unique_texts:
        has_pt = any(w in t.lower() for w in ["ção", "ões", "ões", "não", "você", "você", "para", "como", "uma", "isso"])
        lang = "pt" if has_pt else "other"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Saved {output_path}")
    print(f"  Samples: {len(unique_texts)}")
    print(f"  Languages (heuristic): {lang_counts}")
    print(f"  File size: {size_mb:.1f} MB")


def main() -> None:
    try:
        texts = load_necent()
        if not texts:
            print("Necent dataset returned 0 samples, trying fallback...")
            texts = load_fallback()
    except Exception as e:
        print(f"Necent dataset unavailable ({e}), trying fallback...")
        try:
            texts = load_fallback()
        except Exception as e2:
            print(f"Fallback dataset also unavailable ({e2})")
            print("Cannot build index without data. Ensure you have:")
            print("  1. HF token with access to gated datasets")
            print("  2. pip install datasets")
            sys.exit(1)

    if not texts:
        print("No texts loaded. Exiting.")
        sys.exit(1)

    build_index(texts)


if __name__ == "__main__":
    main()
