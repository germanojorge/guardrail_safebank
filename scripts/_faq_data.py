#!/usr/bin/env python3
"""Shared FAQ data loading utilities for eval and fine-tuning scripts.

Extracted from finetune_itau_embedding.py so both eval_retrieval.py and the
fine-tuner can import without side-effects from __main__ blocks.
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de datasets/transformers

from datasets import load_dataset
from sentence_transformers import InputExample
from sentence_transformers.sentence_transformer import evaluation

DATASET_NAME = "Itau-Unibanco/FAQ_BACEN"


def load_faq_train_for_ingest() -> list[dict[str, str]]:
    """Train-split rows for Qdrant ingestion.

    The HF ``test`` split is held out for evaluation — frozen queries live in
    ``data/eval/faq_bacen_eval.jsonl`` (refresh via ``eval_retrieval.py --freeze``).
    """
    print(f"Loading {DATASET_NAME} (train split only; test held out for eval) ...")
    ds_train = load_dataset(DATASET_NAME, split="train")

    rows: list[dict[str, str]] = []
    for idx, row in enumerate(ds_train):
        question = row["questions"].strip()
        answer = row["answers"].strip()
        if not question or not answer:
            continue
        rows.append(
            {
                "doc_id": f"train_{idx}",
                "question": question,
                "answer": answer,
            }
        )

    print(f"Train rows for ingest: {len(rows)}")
    return rows


def load_faq_data() -> tuple[list[InputExample], dict[str, str], list[str], list[str]]:
    """Load Itaú FAQ and prepare train examples + eval corpus/queries.

    Returns:
        train_examples: List of InputExample(question, answer) for training
        corpus: Dict mapping doc_id -> answer text (all answers from train+test)
        queries: List of question texts from test split
        relevant_docs: List of doc_ids that are correct for each query (same index)
    """
    print(f"Loading {DATASET_NAME} ...")
    ds_train = load_dataset(DATASET_NAME, split="train")
    ds_test = load_dataset(DATASET_NAME, split="test")

    train_examples: list[InputExample] = []
    for row in ds_train:
        q = row["questions"].strip()
        a = row["answers"].strip()
        if q and a:
            train_examples.append(InputExample(texts=[q, a]))

    print(f"Train examples: {len(train_examples)}")

    # Corpus = all answers (train answers are distractors, test answers are gold)
    corpus: dict[str, str] = {}
    for i, row in enumerate(ds_train):
        corpus[f"train_{i}"] = row["answers"].strip()
    for i, row in enumerate(ds_test):
        corpus[f"test_{i}"] = row["answers"].strip()

    # Queries from test split; gold doc_id = test_{i}
    queries: list[str] = []
    relevant_docs: list[str] = []
    for i, row in enumerate(ds_test):
        q = row["questions"].strip()
        if q:
            queries.append(q)
            relevant_docs.append(f"test_{i}")

    print(f"Corpus size: {len(corpus)}")
    print(f"Test queries: {len(queries)}")

    return train_examples, corpus, queries, relevant_docs


def build_evaluator(
    corpus: dict[str, str],
    queries: list[str],
    relevant_docs: list[str],
    name: str = "itau-faq-ir",
) -> evaluation.InformationRetrievalEvaluator:
    """Build IR evaluator mapping test questions to their correct answers."""
    queries_dict: dict[str, str] = {}
    relevant_docs_map: dict[str, set[str]] = {}

    for q, doc_id in zip(queries, relevant_docs):
        if q in relevant_docs_map:
            relevant_docs_map[q].add(doc_id)
        else:
            queries_dict[q] = q
            relevant_docs_map[q] = {doc_id}

    return evaluation.InformationRetrievalEvaluator(
        queries=queries_dict,
        corpus=corpus,
        relevant_docs=relevant_docs_map,
        name=name,
        show_progress_bar=True,
    )
