"""
JailbreakValidator — multi-layer prompt injection detector (v3).

Four-layer layered defense with early-exit:
  Layer 1a: deterministic regex rules with named, explainable patterns (<1ms)
  Layer 1b: POS tagger + spaCy word-vector similarity (~20-40ms CPU)
  Layer 1c: semantic index with MiniLM embeddings (~10ms CPU)
  Layer 2:  Prompt-Guard-2 classifier (~300ms CPU, last resort)

`details` keys populated by `run()`:
- `layer_caught`: "regex" | "pos_tagger" | "semantic" | "prompt_guard" | None
- `matched_rules`: list[str] — rule names that matched (L1a only)
- `pos_tags`: list[tuple[str, str]] | None — (token, tag) from POS tagger
- `pos_patterns_matched`: list[str] | None — POS pattern names that fired
- `semantic_score`: float | None — max cosine similarity from semantic index
- `semantic_match_text`: str | None — closest match text from index
- `prompt_guard_score`: float | None — classifier confidence score
- `threshold`: float — classifier threshold used
- `rules_checked`: int — number of regex rules checked
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Mapping

import numpy as np

from .base import ValidatorResult


# ── L1a: Regex Rules ─────────────────────────────────────────────────────────
#
# Each rule is a (name, pattern) tuple. The name is surfaced in
# `details["matched_rules"]` for auditability and compliance reporting.

_FLAGS = re.IGNORECASE | re.UNICODE

_RULES: list[tuple[str, str]] = [
    (
        "sobrescrita_instrucoes",
        r"\b(ignore|desconsidere|esque[çc]a|não siga|anule|forget|disregard)\b"
        r".{0,40}"
        r"\b(instru[çc][oõ]es|regras|pol[ií]tica|sistema|limites|restri[çc][oõ]es|"
        r"previous instructions|rules|policy|system|constraints)\b",
    ),
    (
        "mudanca_papel",
        r"\b(aja como|aga como|haja como|finja (que você é|ser)|responda como|se comporte como|"
        r"pretend (you are|to be)|act as|you are now)\b"
        r".{0,30}"
        r"\b(admin|administrador|administradora|desenvolvedor|desenvolvedora|sistema|sem (regras|restri[çc][oõ]es)|"
        r"unrestricted|developer|DAN|no restrictions)\b",
    ),
    (
        "extracao_instrucoes",
        r"\b(mostre|revele|liste|exiba|repita|show|reveal|repeat|tell me)\b"
        r".{0,30}"
        r"\b(prompt|instru[çc][oõ]es (internas|que você)|regras (que você|do sistema)|"
        r"system (prompt|message|instructions)|internal instructions)\b",
    ),
    (
        "conflito_politica",
        r"\b(responda (sem filtros?|mesmo que|independente de)|"
        r"não aplique (regras|seguran[çc]a)|"
        r"respond without filters|bypass your safety)\b",
    ),
    (
        "encadeamento_suspeito",
        r"\b(finja|aja como|aga como|haja como)\b.{0,60}\b(me (diga|passe|revele))\b",
    ),
    (
        "modo_dan",
        r"\b(DAN|developer mode|modo desenvolvedor|do anything now)\b",
    ),
    (
        "palavras_chave_isoladas",
        r"\b(jailbreak|override|bypass)\b",
    ),
]

_COMPILED_RULES: list[tuple[str, re.Pattern]] = [(name, re.compile(pattern, _FLAGS)) for name, pattern in _RULES]


# ── L1b: POS Pattern Sets ───────────────────────────────────────────────────
#
# Each pattern is a named rule that uses POS tagger + spaCy word vectors for
# cosine similarity between input tokens and reference centroid vectors.

_POS_SOBRESCRITA_VERBS: list[str] = [
    "ignorar",
    "desconsiderar",
    "esquecer",
    "anular",
]
_POS_SOBRESCRITA_NOUNS: list[str] = [
    "instrução",
    "instruções",
    "regra",
    "regras",
    "política",
    "políticas",
    "sistema",
    "limite",
    "restrição",
    "restrições",
]

_POS_MUDANCA_VERBS: list[str] = [
    "agir",
    "fingir",
    "responder",
    "comportar",
]
_POS_MUDANCA_NOUNS: list[str] = [
    "administrador",
    "desenvolvedor",
    "sistema",
]

_POS_EXTRACAO_VERBS: list[str] = [
    "mostrar",
    "revelar",
    "exibir",
    "listar",
    "repetir",
]
_POS_EXTRACAO_NOUNS: list[str] = [
    "prompt",
    "instrução",
    "regra",
    "política",
]


def _pos_vocab_mean(nlp, tokens: list[str]) -> np.ndarray | None:
    """Return mean word vector for a list of tokens. None if no token has vector."""
    vecs = []
    for t in tokens:
        lex = nlp.vocab[t]
        if lex.has_vector:
            vecs.append(lex.vector)
            continue
        lex_lower = nlp.vocab[t.lower()]
        if lex_lower.has_vector:
            vecs.append(lex_lower.vector)
    if not vecs:
        return None
    return np.mean(vecs, axis=0)


class PosPatternMatcher:
    """Apply POS-tagged + spaCy similarity rules to detect jailbreak intent.

    Uses word vectors from spaCy `pt_core_news_lg` for cosine similarity
    between input tokens and reference centroids.
    """

    def __init__(self, threshold: float = 0.55) -> None:
        self.threshold = threshold
        self._nlp = self._load_nlp()
        self._centroids = self._compute_centroids()

    @staticmethod
    def _load_nlp():
        import spacy

        return spacy.load("pt_core_news_lg", disable=["parser", "ner", "lemmatizer", "textcat", "attribute_ruler"])

    def _token_vector(self, token: str) -> np.ndarray | None:
        lex = self._nlp.vocab[token]
        if lex.has_vector:
            return lex.vector
        lex_lower = self._nlp.vocab[token.lower()]
        if lex_lower.has_vector:
            return lex_lower.vector
        return None

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _compute_centroids(self) -> dict[str, np.ndarray | None]:
        return {
            "sobrescrita_verbs": _pos_vocab_mean(self._nlp, _POS_SOBRESCRITA_VERBS),
            "sobrescrita_nouns": _pos_vocab_mean(self._nlp, _POS_SOBRESCRITA_NOUNS),
            "mudanca_verbs": _pos_vocab_mean(self._nlp, _POS_MUDANCA_VERBS),
            "mudanca_nouns": _pos_vocab_mean(self._nlp, _POS_MUDANCA_NOUNS),
            "extracao_verbs": _pos_vocab_mean(self._nlp, _POS_EXTRACAO_VERBS),
            "extracao_nouns": _pos_vocab_mean(self._nlp, _POS_EXTRACAO_NOUNS),
        }

    def match(self, tagged_tokens: list[tuple[str, str]]) -> tuple[bool, list[str]]:
        """Run all POS patterns against tagged tokens.

        Returns (matched, pattern_names).
        """
        patterns: dict[str, bool] = {
            "pos_sobrescrita": self._pattern_sobrescrita(tagged_tokens),
            "pos_mudanca_papel": self._pattern_mudanca_papel(tagged_tokens),
            "pos_extracao": self._pattern_extracao(tagged_tokens),
            "pos_conflito": self._pattern_conflito(tagged_tokens),
        }
        matched = [name for name, hit in patterns.items() if hit]
        return bool(matched), matched

    def _best_sim(self, token_vec: np.ndarray, centroid) -> float:
        if centroid is None:
            return 0.0
        return self._cosine(token_vec, centroid)

    def _pattern_sobrescrita(self, tagged: list[tuple[str, str]]) -> bool:
        """VERB similar to {ignorar, desconsiderar, esquecer, anular} > threshold."""
        for token, tag in tagged:
            if tag == "VERB":
                tv = self._token_vector(token)
                if tv is not None:
                    sim = self._best_sim(tv, self._centroids["sobrescrita_verbs"])
                    if sim > self.threshold:
                        return True
        return False

    def _pattern_mudanca_papel(self, tagged: list[tuple[str, str]]) -> bool:
        """VERB similar to {agir, fingir, responder} + ADP 'como' + NOUN/PROPN similar to {admin, ...}."""
        has_verb = False
        has_como = any(token.lower() == "como" and tag == "ADP" for token, tag in tagged)
        has_target_noun = False

        for token, tag in tagged:
            tv = self._token_vector(token)
            if tv is None:
                continue
            if tag == "VERB":
                sim = self._best_sim(tv, self._centroids["mudanca_verbs"])
                if sim > self.threshold:
                    has_verb = True
            if tag in ("NOUN", "PROPN"):
                sim = self._best_sim(tv, self._centroids["mudanca_nouns"])
                if sim > self.threshold:
                    has_target_noun = True

        return has_verb and has_como and has_target_noun

    def _pattern_extracao(self, tagged: list[tuple[str, str]]) -> bool:
        """VERB similar to {mostrar, revelar, exibir, listar, repetir}
        + NOUN similar to {prompt, instrução, regra, política}."""
        has_verb = False
        has_noun = False

        for token, tag in tagged:
            tv = self._token_vector(token)
            if tv is None:
                continue
            if tag == "VERB":
                sim = self._best_sim(tv, self._centroids["extracao_verbs"])
                if sim > self.threshold:
                    has_verb = True
            if tag == "NOUN":
                sim = self._best_sim(tv, self._centroids["extracao_nouns"])
                if sim > self.threshold:
                    has_noun = True

        return has_verb and has_noun

    def _pattern_conflito(self, tagged: list[tuple[str, str]]) -> bool:
        """'responda' (VERB) + 'sem' (ADP) + 'filtros' (NOUN) detected via tags."""
        has_responda = False
        has_sem = False
        has_filtros = False

        for token, tag in tagged:
            tlower = token.lower()
            if tag == "VERB" and tlower == "responda":
                has_responda = True
            if tag == "ADP" and tlower == "sem":
                has_sem = True
            if tag == "NOUN" and tlower == "filtros":
                has_filtros = True

        return has_responda and has_sem and has_filtros


# ── L1c: Semantic Index ─────────────────────────────────────────────────────


class SemanticIndex:
    """Brute-force cosine similarity search over pre-computed jailbreak embeddings."""

    def __init__(self, index_path: str, embedding_model_name: str, threshold: float) -> None:
        self.threshold = threshold
        self._texts: list[str] = []
        self._embeddings: np.ndarray | None = None
        self._model = self._load_embedding_model(embedding_model_name)
        if os.path.exists(index_path):
            self._load_index(index_path)

    @staticmethod
    def _load_embedding_model(model_name: str):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)

    def _load_index(self, path: str) -> None:
        data = np.load(path, allow_pickle=True)
        self._texts = list(data["texts"])
        self._embeddings = data["embeddings"]
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        self._embeddings = self._embeddings / norms

    def is_loaded(self) -> bool:
        return self._embeddings is not None and len(self._texts) > 0

    def search(self, text: str) -> tuple[bool, float, str]:
        """Return (matched, max_similarity, matched_text)."""
        if not self.is_loaded():
            return False, 0.0, ""

        query_vec = self._model.encode([text], normalize_embeddings=True)[0]
        similarities = np.dot(self._embeddings, query_vec)
        best_idx = int(np.argmax(similarities))
        max_sim = float(similarities[best_idx])

        if max_sim >= self.threshold:
            return True, max_sim, self._texts[best_idx]
        return False, max_sim, ""


# ── L1b + L1c: Model Loaders ─────────────────────────────────────────────────


def _load_tagger():
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    tokenizer = AutoTokenizer.from_pretrained("Emanuel/porttagger-news-base")
    model = AutoModelForTokenClassification.from_pretrained("Emanuel/porttagger-news-base")
    return pipeline(
        "token-classification",
        model=model,
        tokenizer=tokenizer,
        aggregation_strategy="simple",
        device=-1,
    )


# ── Validator ────────────────────────────────────────────────────────────────


_SEMANTIC_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class JailbreakValidator:
    name = "jailbreak"

    def __init__(
        self,
        threshold: float = 0.85,
        pos_threshold: float = 0.55,
        semantic_threshold: float = 0.80,
        pipeline=None,
        tagger_model=None,
        semantic_index_path: str = "data/jailbreak_index.npz",
        use_pos_tagger: bool = True,
        use_semantic: bool = True,
        use_prompt_guard: bool = True,
    ) -> None:
        self.threshold = threshold
        self.pos_threshold = pos_threshold
        self.semantic_threshold = semantic_threshold
        self.use_pos_tagger = use_pos_tagger
        self.use_semantic = use_semantic
        self.use_prompt_guard = use_prompt_guard

        self._pipeline = pipeline if pipeline is not None else self._load_pipeline()

        if use_pos_tagger:
            self._tagger = tagger_model if tagger_model is not None else _load_tagger()
            self._pos_matcher = PosPatternMatcher(threshold=pos_threshold)
        else:
            self._tagger = None
            self._pos_matcher = None

        if use_semantic:
            self._semantic_index = SemanticIndex(
                index_path=semantic_index_path,
                embedding_model_name=_SEMANTIC_MODEL_NAME,
                threshold=semantic_threshold,
            )
        else:
            self._semantic_index = None

    @staticmethod
    def _load_pipeline():
        from transformers import pipeline

        return pipeline(
            "text-classification",
            model="meta-llama/Llama-Prompt-Guard-2-86M",
            device=-1,
        )

    def _base_details(self) -> dict[str, Any]:
        return {
            "layer_caught": None,
            "matched_rules": [],
            "pos_tags": None,
            "pos_patterns_matched": None,
            "semantic_score": None,
            "semantic_match_text": None,
            "prompt_guard_score": None,
            "threshold": self.threshold,
            "rules_checked": len(_RULES),
        }

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()

        if not text.strip():
            details = self._base_details()
            return ValidatorResult(
                passed=True,
                category="jailbreak",
                score=None,
                details=details,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # ── L1a: Regex Fast-Path Gate ────────────────────────────────────
        matched_rules = [name for name, pattern in _COMPILED_RULES if pattern.search(text)]

        if matched_rules:
            details = self._base_details()
            details["rule_violated"] = "jailbreak"
            details["layer_caught"] = "regex"
            details["matched_rules"] = matched_rules
            return ValidatorResult(
                passed=False,
                category="jailbreak",
                score=1.0,
                details=details,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # ── L1b: POS Tagger ─────────────────────────────────────────────
        if self.use_pos_tagger and self._tagger is not None:
            try:
                ner_results = self._tagger(text)
                tagged_tokens: list[tuple[str, str]] = [(r["word"], r["entity_group"]) for r in ner_results]
                matched, patterns_hit = self._pos_matcher.match(tagged_tokens)
                if matched:
                    details = self._base_details()
                    details["rule_violated"] = "jailbreak"
                    details["layer_caught"] = "pos_tagger"
                    details["pos_tags"] = tagged_tokens
                    details["pos_patterns_matched"] = patterns_hit
                    return ValidatorResult(
                        passed=False,
                        category="jailbreak",
                        score=1.0,
                        details=details,
                        latency_ms=(time.perf_counter() - t0) * 1000,
                    )
            except Exception:
                pass  # fail-open: POS tagger error falls through to next layer

        # ── L1c: Semantic Index ──────────────────────────────────────────
        if self.use_semantic and self._semantic_index is not None and self._semantic_index.is_loaded():
            try:
                hit, sim, match_text = self._semantic_index.search(text)
                if hit:
                    details = self._base_details()
                    details["rule_violated"] = "jailbreak"
                    details["layer_caught"] = "semantic"
                    details["semantic_score"] = sim
                    details["semantic_match_text"] = match_text
                    return ValidatorResult(
                        passed=False,
                        category="jailbreak",
                        score=float(sim),
                        details=details,
                        latency_ms=(time.perf_counter() - t0) * 1000,
                    )
            except Exception:
                pass  # fail-open: semantic index error falls through

        # ── L2: Prompt-Guard-2 ───────────────────────────────────────────
        if not self.use_prompt_guard:
            details = self._base_details()
            details["use_prompt_guard"] = False
            return ValidatorResult(
                passed=True,
                category="jailbreak",
                score=None,
                details=details,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            result = self._pipeline(text)[0]
        except Exception:
            return ValidatorResult(
                passed=False,
                category="jailbreak",
                score=1.0,
                details={
                    "error": "prompt_guard_pipeline_failed",
                    "stage": "jailbreak_prompt_guard",
                    "matched_rules": [],
                },
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        label: str = result["label"]
        score: float = result["score"]

        is_malicious = label.upper() in {"LABEL_1", "INJECTION", "MALICIOUS", "JAILBREAK"}

        if is_malicious and score >= self.threshold:
            details = self._base_details()
            details["rule_violated"] = "jailbreak"
            details["layer_caught"] = "prompt_guard"
            details["prompt_guard_score"] = score
            return ValidatorResult(
                passed=False,
                category="jailbreak",
                score=score,
                details=details,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        details = self._base_details()
        details["prompt_guard_score"] = score
        if self.use_semantic and self._semantic_index is not None and self._semantic_index.is_loaded():
            try:
                _, sim_benign, match_benign = self._semantic_index.search(text)
                details["semantic_score"] = sim_benign
                details["semantic_match_text"] = match_benign
            except Exception:
                pass

        return ValidatorResult(
            passed=True,
            category="jailbreak",
            score=None,
            details=details,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
