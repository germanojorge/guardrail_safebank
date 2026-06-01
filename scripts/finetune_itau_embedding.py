#!/usr/bin/env python3
"""Fine-tune sentence-transformer on Itaú FAQ dataset for banking domain embeddings.

Trains with MultipleNegativesRankingLoss using (question, answer) pairs.
Evaluates with InformationRetrievalEvaluator on held-out test split.

Usage:
    uv run python scripts/finetune_itau_embedding.py

Output:
    models/itau-embedding-finetuned/ — fine-tuned model
    models/itau-embedding-eval/ — evaluation results
"""

from __future__ import annotations

import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de importar datasets/transformers

import argparse
import os
from datetime import datetime

from datasets import load_dataset
from sentence_transformers import (
    InputExample,
    SentenceTransformer,
    losses,
    evaluation,
)
from torch.utils.data import DataLoader

_DEFAULT_BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_OUTPUT_DIR = "models/itau-embedding-finetuned"
_EVAL_DIR = "models/itau-embedding-eval"


def load_faq_data() -> tuple[list[InputExample], dict[str, str], list[str], list[str]]:
    """Load Itaú FAQ and prepare train examples + eval corpus/queries.

    Returns:
        train_examples: List of InputExample(question, answer) for training
        corpus: Dict mapping doc_id -> answer text (all answers from train+test)
        queries: List of question texts from test split
        relevant_docs: List of doc_ids that are correct for each query
    """
    print("Loading Itau-Unibanco/FAQ_BACEN ...")
    ds_train = load_dataset("Itau-Unibanco/FAQ_BACEN", split="train")
    ds_test = load_dataset("Itau-Unibanco/FAQ_BACEN", split="test")

    # Build training examples: (question, answer)
    train_examples: list[InputExample] = []
    for i, row in enumerate(ds_train):
        q = row["questions"].strip()
        a = row["answers"].strip()
        if q and a:
            train_examples.append(InputExample(texts=[q, a]))

    print(f"Train examples: {len(train_examples)}")

    # Build corpus from ALL answers (train + test) for evaluation
    corpus: dict[str, str] = {}
    for i, row in enumerate(ds_train):
        doc_id = f"train_{i}"
        corpus[doc_id] = row["answers"].strip()
    for i, row in enumerate(ds_test):
        doc_id = f"test_{i}"
        corpus[doc_id] = row["answers"].strip()

    # Build queries from test split
    queries: list[str] = []
    relevant_docs: list[str] = []
    for i, row in enumerate(ds_test):
        q = row["questions"].strip()
        if q:
            queries.append(q)
            # The correct answer is in the corpus at test_{i}
            relevant_docs.append(f"test_{i}")

    print(f"Corpus size: {len(corpus)}")
    print(f"Test queries: {len(queries)}")

    return train_examples, corpus, queries, relevant_docs


def build_evaluator(
    corpus: dict[str, str],
    queries: list[str],
    relevant_docs: list[str],
) -> evaluation.InformationRetrievalEvaluator:
    """Build IR evaluator mapping test questions to their correct answers."""
    # Map query text -> set of relevant doc_ids
    # Since queries may not be unique, we use the query text as key
    queries_dict: dict[str, str] = {}
    relevant_docs_map: dict[str, set[str]] = {}

    for q, doc_id in zip(queries, relevant_docs):
        # If duplicate query, append doc_id to existing set
        if q in relevant_docs_map:
            relevant_docs_map[q].add(doc_id)
        else:
            queries_dict[q] = q
            relevant_docs_map[q] = {doc_id}

    return evaluation.InformationRetrievalEvaluator(
        queries=queries_dict,
        corpus=corpus,
        relevant_docs=relevant_docs_map,
        name="itau-faq-ir",
        show_progress_bar=True,
    )


def train(
    base_model: str = _DEFAULT_BASE_MODEL,
    output_dir: str = _OUTPUT_DIR,
    eval_dir: str = _EVAL_DIR,
    epochs: int = 3,
    batch_size: int = 16,
    warmup_steps: int = 100,
    eval_steps: int = 500,
    save_steps: int = 500,
    learning_rate: float = 2e-5,
) -> None:
    """Fine-tune embedding model on Itaú FAQ."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(eval_dir, exist_ok=True)

    print(f"Base model: {base_model}")
    print(f"Output dir: {output_dir}")
    print(f"Epochs: {epochs}, Batch size: {batch_size}, LR: {learning_rate}")

    # Load data
    train_examples, corpus, queries, relevant_docs = load_faq_data()

    # Init model
    model = SentenceTransformer(base_model)
    print(f"Model dimension: {model.get_sentence_embedding_dimension()}")

    # Training dataloader
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
    train_loss = losses.MultipleNegativesRankingLoss(model)

    # Evaluator
    ir_evaluator = build_evaluator(corpus, queries, relevant_docs)

    # Train
    print("\n=== Starting training ===")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        evaluator=ir_evaluator,
        evaluation_steps=eval_steps,
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": learning_rate},
        output_path=output_dir,
        save_best_model=True,
        checkpoint_path=os.path.join(output_dir, "checkpoints"),
        checkpoint_save_steps=save_steps,
    )

    # Final evaluation
    print("\n=== Final evaluation ===")
    model.save(output_dir)
    results = ir_evaluator(model, output_path=eval_dir)

    print("\n=== Results ===")
    print(f"Model saved to: {output_dir}")
    print(f"Eval results saved to: {eval_dir}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")

    # Print key metrics
    for k in [1, 3, 5, 10]:
        key = f"itau-faq-ir_cosine_ndcg@{k}"
        if key in results:
            print(f"  nDCG@{k}: {results[key]:.4f}")
        key_map = "itau-faq-ir_cosine_map@k"
        if key_map in results:
            print(f"  MAP: {results[key_map]:.4f}")
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune embeddings on Itaú FAQ")
    parser.add_argument("--base-model", default=_DEFAULT_BASE_MODEL, help="Base sentence-transformer model")
    parser.add_argument("--output-dir", default=_OUTPUT_DIR, help="Where to save the fine-tuned model")
    parser.add_argument("--eval-dir", default=_EVAL_DIR, help="Where to save evaluation results")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Training batch size")
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps")
    parser.add_argument("--eval-steps", type=int, default=500, help="Evaluate every N steps")
    parser.add_argument("--save-steps", type=int, default=500, help="Save checkpoint every N steps")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="Learning rate")
    args = parser.parse_args()

    train(
        base_model=args.base_model,
        output_dir=args.output_dir,
        eval_dir=args.eval_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        warmup_steps=args.warmup_steps,
        eval_steps=args.eval_steps,
        save_steps=args.save_steps,
        learning_rate=args.learning_rate,
    )


if __name__ == "__main__":
    main()
