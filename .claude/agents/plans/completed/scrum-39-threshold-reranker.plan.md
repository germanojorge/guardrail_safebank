# Plan: Retrieval — Score Threshold + Cross-Encoder Reranker (measured) (SCRUM-39)

## Summary

Add two retrieval-quality levers to the banking RAG path, each **gated by measurement** (building-rigorously §3 — measure, don't assume): (1) a **cosine score threshold** so off-topic queries return an empty top-k and the chatbot answers "não tenho essa informação" instead of hallucinating on junk context; (2) a **cross-encoder reranker** (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) that retrieves top-N≈20 dense then reranks to top-3. Both are wired through the **single eval harness** (`scripts/eval_retrieval.py`, the "caminho único de métrica" from PRD §6) to produce a `dense-only vs +threshold vs +reranker` before/after table on the frozen `faq_bacen` split; **only the variant with a positive delta ships** to `config.yaml`, the loser becomes a documented talking point (§7). Production wiring follows the existing Protocol/adapter + DI pattern (`EmbeddingProvider`/`VectorStore` → `_create_components`); `rerank_ms` joins the latency breakdown in diagnostics.

## User Story

As an atendente-bot bancário
I want to drop irrelevant context and re-rank retrieved candidates
So that answer quality rises and I avoid hallucinating financial advice on junk chunks.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (extends SCRUM-37/38 harness + production retrieve path) + DATA/DECISION |
| Complexity | MEDIUM-HIGH |
| Systems Affected | `scripts/eval_retrieval.py`, new `guardrails/adapters/reranker.py`, `guardrails/pipeline/nodes.py`, `guardrails/pipeline/graph.py`, `guardrails/api/app.py`, `guardrails/api/schemas.py`, `guardrails/adapters/vector_store.py`, `config.yaml`, `models/eval/`, tests, docs |
| Jira Issue | SCRUM-39 |
| Blocked by | SCRUM-37 (harness) — DONE; SCRUM-38 (bake-off, e5-base shipped) — DONE |
| Blocks | Story 4 (docs need the before/after deltas) |

---

## Baseline numbers to gate against (no doc drift — building-rigorously §4)

Current shipped model: `intfloat/multilingual-e5-base` (768-dim, `config.yaml`), `prefix_style="e5"`.

| Split | n_corpus / n_q | recall@3 | recall@5 | MRR@10 | nDCG@10 |
|-------|----------------|----------|----------|--------|---------|
| `faq_bacen` (external, headline) | 1678 / 373 | — | **0.7480** | **0.5885** | **0.6390** |
| `banking_kb` (closed-loop, demo) | 29 / 16 | **0.875** | **0.9375** | **0.8281** | **0.8558** |

Reranker/threshold **ship only if** they beat these on `faq_bacen` **and** do not regress `banking_kb` (the demo). Source: `models/eval/faq_bacen__*e5-base*.json`, `models/eval/banking_kb__*e5-base*.json`.

---

## Critical Design Decisions

### D1 — The reranker cannot use `InformationRetrievalEvaluator` (it embeds, it doesn't rerank)

`run_eval` (`scripts/eval_retrieval.py:166`) delegates all metric computation to `InformationRetrievalEvaluator`, which scores a **bi-encoder's** own embeddings. A cross-encoder re-orders an existing candidate list — there is no embedding to hand the evaluator. **Therefore we need a manual retrieve→(threshold)→(rerank)→rank→metrics path** with our own IR metric functions (recall@k, RR, nDCG, AP).

**Built-in correctness check (anti-tautology, §1/§3):** run the *dense-only* path through the **same** manual code (no threshold, no reranker) and assert its numbers match `InformationRetrievalEvaluator` on the frozen split (e5-base recall@5 ≈ 0.7480). If the manual metrics reproduce the trusted evaluator on dense-only, the metric code is validated independently of the reranker — then the reranker delta is trustworthy. This is the non-negotiable guard against "I wrote the metric and the matcher in one flow."

### D2 — Threshold needs an off-topic set from a different source (§1)

A cosine threshold's value is measured by two competing quantities:
- **Recall retention** on on-topic queries (`faq_bacen` test queries — gold doc must survive the cut).
- **Off-topic rejection rate** on queries with **no** gold doc (should return empty).

E5 has a *narrow* cosine distribution (normalized embeddings) — off-topic queries still score ~0.75–0.80, so the threshold is non-obvious and **must be swept, not guessed**. Off-topic queries come from a **different source than the corpus**: the hardcoded non-banking seeds already curated in `guardrails/validators/out_of_scope.py` (`_OUT_OF_SCOPE_SEEDS` — "Como fazer bolo de chocolate?", "Qual a capital da Austrália?", …). Sweep emits `threshold | recall@3 retained | off-topic rejection %`; ship the knee (max rejection, ≤ small recall loss), or document "no good operating point" as the §7 talking point.

### D3 — Threshold lives in `search` (pushdown) + enforced in `retrieve`

AC names both `retrieve` (`nodes.py:92`) and `search` (`vector_store.py:97`). Add `score_threshold: float | None = None` to `VectorStore.search` (Qdrant supports native `score_threshold` in `query_points`; `InMemoryVectorStore` filters in Python). `retrieve` passes the configured threshold through and requests `top_k=top_n` (≈20) when a reranker is active. Empty result needs **no new prompt** — `CHATBOT_SYSTEM_PROMPT` (`nodes.py:22-25`) already says "Se não souber a resposta, diga que não tem essa informação e sugira falar com um gerente"; an empty `context_block` triggers exactly that.

### D4 — Order in `retrieve`: dense top-N → cosine threshold → rerank → top-K

Threshold filters on **cosine** (the AC's "cosine mínimo") at the dense stage; the cross-encoder then re-orders survivors and we slice top-3. Document that rerank scores are not cosine — the threshold gates dense recall, the reranker gates ordering.

---

## Patterns to Follow

### Protocol + concrete + in-process fake (mirror for the reranker)
```python
# SOURCE: guardrails/adapters/vector_store.py:28-37, 121-159
@runtime_checkable
class VectorStore(Protocol):
    def search(self, query_vector: list[float], top_k: int = 3) -> list[SearchHit]: ...

class InMemoryVectorStore:  # pure-Python fake for tests, no model load
    def search(self, query_vector, top_k=3): ...
```
The reranker gets the same shape: `Reranker` Protocol, `CrossEncoderReranker` (lazy model load via `_create_model` staticmethod, like `SentenceTransformerProvider._create_model`, `embedding.py:48-52`), and a deterministic `IdentityReranker`/`StubReranker` fake for tests.

### Lazy heavy-model load, model-injectable constructor
```python
# SOURCE: guardrails/adapters/embedding.py:33-52
def __init__(self, model: Any = None, model_name: str = ..., device: str = "cpu", ...):
    self.model = model if model is not None else self._create_model(model_name, device)
@staticmethod
def _create_model(model_name, device):
    from sentence_transformers import SentenceTransformer  # lazy import
    return SentenceTransformer(model_name, device=device)
```
CrossEncoder analog: `from sentence_transformers import CrossEncoder`.

### Node factory closure with injected optional deps (graceful when absent)
```python
# SOURCE: guardrails/pipeline/nodes.py:32-43, 92-124
def build_nodes(..., embedding=None, vector_store=None, out_of_scope=None):
    def retrieve(state):
        if embedding is not None and vector_store is not None:
            ...  # try/except around search, diagnostics with *_ms keys
```
Add `reranker=None`, `score_threshold=None`, `retrieve_top_n=RETRIEVE_TOP_N` to the closure params; keep the `try/except → []` resilience and the `retrieve_*_ms` diagnostics convention.

### DI through `_create_components` + `build_graph`
```python
# SOURCE: guardrails/api/app.py:27-95  +  guardrails/pipeline/graph.py:21-84
embedding = SentenceTransformerProvider(model_name=emb_cfg.get("model", ...), ...)
graph = build_graph(..., embedding=embedding, vector_store=vector_store)
```
Reranker built from a new `retrieval` config block, threaded `build_graph(..., reranker=...)` → `build_nodes(..., reranker=...)`. Default `None` (feature off) so every existing test/path is unaffected.

### Harness: pure functions, env_bootstrap first, stable run-JSON keys
```python
# SOURCE: scripts/eval_retrieval.py:27 (env_bootstrap first), :252-263 (pure extract_metrics),
#         :346-359 (run payload — extend, keep keys stable)
import guardrails.env_bootstrap  # noqa: F401  # MUST precede datasets/transformers
```
New IR metric helpers are **pure** (mirror `extract_metrics`/`render_markdown`, `:252-281`) → unit-testable with no network.

### Tests: protocol runtime-check + mocked client, no live container
```python
# SOURCE: tests/unit/test_vector_store.py:11-37
def test_in_memory_protocol_runtime_check():
    assert isinstance(InMemoryVectorStore(), VectorStore)
```
Heavy model paths stay behind `@pytest.mark.slow`; metric math + threshold filtering + rerank plumbing tested with fakes/mocks (markers in `pyproject.toml`: `slow`, `network`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/eval_retrieval.py` | UPDATE | Pure IR metric helpers (`recall_at_k`, `reciprocal_rank`, `ndcg_at_k`, `average_precision`, `rank_metrics`); manual `run_eval_manual(... reranker, score_threshold, top_n)`; wire the reserved `--reranker`/`--threshold` flags (`:325-327`) + `--top-n`; dense-only consistency assertion vs `InformationRetrievalEvaluator` |
| `scripts/eval_retrieval.py` | UPDATE | `--threshold-sweep` mode: on-topic recall retention vs off-topic rejection table using `_OUT_OF_SCOPE_SEEDS` |
| `guardrails/adapters/reranker.py` | CREATE | `Reranker` Protocol + `CrossEncoderReranker` + `IdentityReranker` fake; `rerank(query, hits, top_k) -> list[SearchHit]` |
| `guardrails/adapters/__init__.py` | UPDATE | Export `Reranker`, `CrossEncoderReranker`, `IdentityReranker` |
| `guardrails/adapters/vector_store.py` | UPDATE | `search(..., score_threshold: float | None = None)` on Protocol + Qdrant (native pushdown) + InMemory (Python filter) |
| `guardrails/pipeline/nodes.py` | UPDATE | `retrieve` gains `reranker`/`score_threshold`/`retrieve_top_n`; flow search(top_n)→threshold→rerank→top_k; `retrieve_rerank_ms` diagnostic |
| `guardrails/pipeline/graph.py` | UPDATE | Thread `reranker`, `score_threshold`, `retrieve_top_n` through `build_graph`→`build_nodes` |
| `guardrails/api/app.py` | UPDATE | Build reranker from `retrieval` config in `_create_components`; pass to `build_graph`; map `rerank` into `LatencyBreakdown` |
| `guardrails/api/schemas.py` | UPDATE | Add `rerank: float | None = None` to `LatencyBreakdown` |
| `config.yaml` | UPDATE | New `retrieval` block: `top_k`, `top_n`, `score_threshold`, `reranker.{enabled,model}` — values set **only after** measurement gate |
| `models/eval/retrieval_before_after.md` | CREATE | Committed before/after table (dense-only vs +threshold vs +reranker) — Story 4 deliverable |
| `models/eval/*.json` | CREATE (generated) | Run records for reranked + threshold-sweep runs |
| `tests/unit/test_eval_retrieval.py` | UPDATE | Unit-test pure IR metric helpers vs hand-computed cases; threshold filter; dense-only manual==evaluator consistency (slow) |
| `tests/unit/test_reranker.py` | CREATE | Protocol runtime-check, `IdentityReranker` behavior, `CrossEncoderReranker` with mocked CrossEncoder (top_k slice, score order) |
| `tests/unit/test_vector_store.py` | UPDATE | `score_threshold` filtering on InMemory + Qdrant `query_points` kwarg pushdown |
| `tests/unit/test_pipeline.py` (or where `retrieve` is tested) | UPDATE | `retrieve` with stub reranker reorders + `retrieve_rerank_ms` present; threshold drops low-score hits → empty chunks |
| `adr/006-local-embeddings.md` | UPDATE | Append measured threshold/reranker deltas (or "did not ship — talking point") |
| `LIMITATIONS.md` | UPDATE | Closed-loop note on threshold off-topic seeds; reranker latency cost; hybrid deferred |

---

## Tasks

Execute in order. Each task is atomic and verifiable. **Measurement tasks (5, 7, 9) gate the production-wiring config; do not hardcode threshold/reranker as "on" before the number proves it.**

### Task 1: Pure IR metric helpers in the harness

- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: Add pure functions operating on a ranked list of doc-ids vs a `set` of relevant ids: `recall_at_k(ranked, relevant, k)`, `reciprocal_rank(ranked, relevant, k=10)`, `ndcg_at_k(ranked, relevant, k=10)`, `average_precision(ranked, relevant, k=10)`, and an aggregator `rank_metrics(per_query_rankings, relevant_docs) -> dict` returning the same keys/shape as `extract_metrics` (`recall@{1,3,5,10}`, `mrr@10`, `ndcg@10`, `map@10`, rounded 4dp). No model, no network.
- **Mirror**: `scripts/eval_retrieval.py:252-281` (`extract_metrics`/`render_markdown` purity + key names)
- **Validate**: `uv run ruff check scripts/eval_retrieval.py`

### Task 2: Manual retrieve→(threshold)→(rerank)→metrics path

- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: `run_eval_manual(model_name, corpus, queries, relevant_docs, *, prefix_style="e5", reranker=None, score_threshold=None, top_n=20)`: embed corpus+queries (reuse `apply_prefixes`, `:153`), for each query compute cosine top_n, optionally drop hits `< score_threshold`, optionally `reranker.rerank(query_text, hits, top_k=top_n)`, then `rank_metrics`. Reranker takes **raw** query/passage text (no E5 prefix — cross-encoders read plain text). Return the same metrics dict shape.
- **Mirror**: `scripts/eval_retrieval.py:166-207` (`run_eval` embedding/prefix flow)
- **Validate**: `uv run ruff check scripts/eval_retrieval.py`

### Task 3: Dense-only consistency check (anti-tautology gate)

- **File**: `tests/unit/test_eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: (a) Unit cases for each metric helper against tiny hand-computed rankings (e.g. relevant at rank 2 → recall@1=0, recall@3=1, RR=0.5, known nDCG). (b) `@pytest.mark.slow` test: `run_eval_manual(e5-base, faq_bacen, reranker=None, score_threshold=None)` reproduces `InformationRetrievalEvaluator` recall@5 ≈ 0.7480 (±0.005). This proves the manual metric code independently before any reranker delta is trusted (building-rigorously §1/§3).
- **Mirror**: `tests/unit/test_eval_retrieval.py` existing mock cases; `@slow` per `pyproject.toml` markers
- **Validate**: `uv run pytest tests/unit/test_eval_retrieval.py -q -m "not slow"`

### Task 4: Reranker adapter

- **File**: `guardrails/adapters/reranker.py`
- **Action**: CREATE
- **Implement**: `@runtime_checkable Reranker(Protocol)` with `rerank(self, query: str, hits: list[SearchHit], top_k: int = 3) -> list[SearchHit]`. `CrossEncoderReranker`: injectable `model`, lazy `_create_model` (`from sentence_transformers import CrossEncoder`), default `model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"`; `rerank` scores `[(query, hit.text) ...]`, returns top_k `SearchHit`s with `score` replaced by the rerank score, descending. `IdentityReranker`: returns `hits[:top_k]` unchanged (deterministic test fake). Empty `hits` → `[]`.
- **Mirror**: `guardrails/adapters/embedding.py:33-52` (lazy load/inject); `guardrails/adapters/vector_store.py:121-159` (fake)
- **Validate**: `uv run ruff check guardrails/adapters/reranker.py`

### Task 5: Reranker bake-off run + before/after table

- **File**: `models/eval/retrieval_before_after.md` (+ run JSONs)
- **Action**: CREATE (generated)
- **Implement**: Via the harness `--reranker cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --top-n 20` on `faq_bacen`, produce rows: `variant | recall@3 | recall@5 | MRR@10 | nDCG@10 | rerank_ms/q` for **dense-only** vs **+reranker**. **Gate (§3):** if reranked recall@5 ≤ 0.7480 (no gain) or absurdly ≈1.0 (suspect bug/leak), do **not** ship — record as talking point. Also run `--dataset banking_kb` anti-regression (must not drop below 0.9375 recall@5 / 0.8281 MRR for the demo).
- **Mirror**: `models/eval/bakeoff_faq_bacen.md` (table artifact style); `scripts/eval_retrieval.py:346-363` (run JSON + render)
- **Validate**: table committed; dense-only row equals the trusted e5-base baseline (regression check); decision (ship / don't) explicitly written

### Task 6: `score_threshold` in `search` (both stores)

- **File**: `guardrails/adapters/vector_store.py`
- **Action**: UPDATE
- **Implement**: Add `score_threshold: float | None = None` to the `VectorStore.search` Protocol, `QdrantStore.search` (pass `score_threshold=score_threshold` into `query_points`), and `InMemoryVectorStore.search` (filter `score >= score_threshold` after sort). Default `None` = current behavior.
- **Mirror**: `guardrails/adapters/vector_store.py:97-118, 139-158`
- **Validate**: `uv run pytest tests/unit/test_vector_store.py -q`

### Task 7: Threshold sweep mode + decision

- **File**: `scripts/eval_retrieval.py` (+ generated sweep artifact)
- **Action**: UPDATE
- **Implement**: `--threshold-sweep` mode: load `faq_bacen` on-topic queries + `_OUT_OF_SCOPE_SEEDS` (import from `guardrails.validators.out_of_scope`) as the no-gold off-topic set; for thresholds in e.g. `0.70..0.90 step 0.02`, report `threshold | recall@3 retained (on-topic) | off-topic rejection %`. Pick the knee (max rejection, ≤ ~2pt recall loss) → that is the `score_threshold` to ship; if no clean knee, ship `null` and document "narrow E5 score distribution gives no safe operating point" (§7).
- **Mirror**: `scripts/eval_retrieval.py:289-363` (CLI + render); off-topic seeds in `guardrails/validators/out_of_scope.py` (`_OUT_OF_SCOPE_SEEDS`)
- **Validate**: sweep table printed + committed; chosen value (or `null`) justified by the numbers

### Task 8: Wire reranker + threshold into the production retrieve node

- **File**: `guardrails/pipeline/nodes.py`, `guardrails/pipeline/graph.py`
- **Action**: UPDATE
- **Implement**: `RETRIEVE_TOP_N = 20`. `build_nodes(..., reranker=None, score_threshold=None, retrieve_top_n=RETRIEVE_TOP_N)`. In `retrieve`: `search(query_vec, top_k=(retrieve_top_n if reranker else RETRIEVE_TOP_K), score_threshold=score_threshold)`; if `reranker`: time `reranker.rerank(state["message"], hits, top_k=RETRIEVE_TOP_K)` into `retrieve_rerank_ms`; else slice `hits[:RETRIEVE_TOP_K]`; `chunks = [h.text for h in hits if h.text]`. Keep the `try/except → []` resilience. Thread the three params through `build_graph` (`graph.py:21-84`).
- **Mirror**: `guardrails/pipeline/nodes.py:92-124` (diagnostics `retrieve_*_ms` convention, try/except)
- **Validate**: `uv run pytest tests/unit/test_pipeline.py -q` (or the file covering `retrieve`)

### Task 9: Config block + DI wiring + diagnostics surface

- **File**: `config.yaml`, `guardrails/api/app.py`, `guardrails/api/schemas.py`
- **Action**: UPDATE
- **Implement**: `config.yaml` `retrieval:` block — `top_k: 3`, `top_n: 20`, `score_threshold: <Task 7 value or null>`, `reranker: {enabled: <Task 5 decision>, model: "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"}`. In `_create_components` (`app.py:27`): read `retrieval` cfg, build `CrossEncoderReranker` iff `enabled`, pass `reranker`/`score_threshold`/`retrieve_top_n` to `build_graph`. Add `rerank: float | None = None` to `LatencyBreakdown` (`schemas.py:8`) and map `rerank=diag.get("retrieve_rerank_ms")` in `app.py:144-150`.
- **Mirror**: `guardrails/api/app.py:27-95` (cfg-driven construction + `build_graph` call); `guardrails/api/schemas.py:8-13`
- **Validate**: `uv run python -c "from guardrails.config import get_config; from guardrails.api.app import _create_components; _create_components(get_config())"` (with `LLM_PROVIDER=mock` if needed) succeeds

### Task 10: Reranker + threshold tests

- **File**: `tests/unit/test_reranker.py` (CREATE), `tests/unit/test_vector_store.py`, pipeline test (UPDATE)
- **Action**: CREATE / UPDATE
- **Implement**: `test_reranker.py`: `isinstance(IdentityReranker(), Reranker)`; `CrossEncoderReranker` with a `MagicMock` CrossEncoder returning fixed scores → asserts top_k slice + descending re-order + score replacement; empty hits → `[]`. `test_vector_store.py`: InMemory drops sub-threshold hits; Qdrant passes `score_threshold` kwarg to `query_points`. Pipeline: stub reranker reverses order → `retrieved_chunks` reflects rerank + `retrieve_rerank_ms` in diagnostics; high `score_threshold` → empty `retrieved_chunks`.
- **Mirror**: `tests/unit/test_vector_store.py:11-40` (mock client, protocol check)
- **Validate**: `uv run pytest tests/unit/ -q -m "not slow"`

### Task 11: Docs — deltas, ADR, limitations (same change, no drift)

- **File**: `adr/006-local-embeddings.md`, `LIMITATIONS.md`, `models/eval/retrieval_before_after.md`
- **Action**: UPDATE / finalize
- **Implement**: Append measured threshold + reranker deltas to ADR-006 (what shipped, what didn't, the number that decided). `LIMITATIONS.md`: threshold off-topic set is hand-curated seeds (different source but small — declare); reranker adds `rerank_ms` latency cost; hybrid BM25+dense deferred (§7 talking point). Ensure every number in docs is copied from `models/eval/*.json` (no doc drift, §4).
- **Mirror**: existing ADR-006 structure; `LIMITATIONS.md` existing sections
- **Validate**: numbers in docs == run JSONs; grep for stale "top-3 dense-only" claims in `docs/`/README and update

### Task 12 (Stretch / if-time): Hybrid BM25+dense

- **File**: harness + `vector_store.py` behind a flag
- **Action**: UPDATE (only if Tasks 1–11 land with time to spare)
- **Implement**: Qdrant native sparse vectors behind `retrieval.hybrid.enabled`; measure via the same manual path; ship only on positive delta, else document as talking point. **Default: NOT built** — call it out explicitly to the user as deferred rather than silently skipping (building-rigorously "say so explicitly").
- **Validate**: measured delta or written-up deferral

---

## Validation

```bash
# Lint
uv run ruff check scripts/ guardrails/ tests/

# Unit tests (mock, no network/model)
uv run pytest tests/unit/ -q -m "not slow"

# Anti-tautology: manual metrics reproduce the trusted evaluator on dense-only
uv run pytest tests/unit/test_eval_retrieval.py -q -m slow   # recall@5 ≈ 0.7480

# Before/after table (slow; HF download of cross-encoder on first run)
uv run python scripts/eval_retrieval.py --reranker cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --top-n 20
uv run python scripts/eval_retrieval.py --threshold-sweep

# Anti-regression on the demo KB before shipping config
uv run python scripts/eval_retrieval.py --reranker cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --dataset banking_kb

# Components still construct with new config block
LLM_PROVIDER=mock uv run python -c "from guardrails.config import get_config; from guardrails.api.app import _create_components; _create_components(get_config())"
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| **Closed metric loop** — I author both the rerank path and its metrics | Dense-only manual path must reproduce `InformationRetrievalEvaluator` (recall@5≈0.7480) before any reranker number is trusted — Task 3 (§1/§3) |
| **Reranker ships without a real win** | Gate on signed delta vs e5-base baseline; loser is a documented talking point, not code (Task 5, §7) |
| **Threshold guessed, not measured** — E5's narrow cosine band | Sweep on/off-topic, pick knee or ship `null`; off-topic from a different source (`_OUT_OF_SCOPE_SEEDS`), declared closed-loop-ish in LIMITATIONS (Task 7, §1) |
| **Reranker regresses the 8-min demo** (`banking_kb` 29 docs) | Mandatory `banking_kb` anti-regression gate ≥ 0.9375 recall@5 / 0.8281 MRR before config flip (Task 5) |
| **Latency blow-up** — cross-encoder on top-20 on CPU | `rerank_ms` exposed in diagnostics; top_n=20 cap; if too slow, lower top_n or ship reranker `enabled:false` with the measured cost as the talking point |
| **E5 prefix leaks into cross-encoder input** | Reranker reads raw `state["message"]`/`hit.text` (no `query:`/`passage:`); prefixes only on the dense stage (D4) |
| **Off-by-one breaking existing retrieve** when reranker absent | `reranker=None` default keeps `top_k=RETRIEVE_TOP_K=3` path byte-identical; all current pipeline tests must stay green (Task 8/10) |
| **Doc drift** between table and shipped config | Numbers copied from `models/eval/*.json`; ADR + LIMITATIONS updated in the same change (Task 11, §4) |

---

## Acceptance Criteria

- [ ] Cosine `score_threshold` enforced in `search` + `retrieve`; off-topic query → empty top-k → "não tenho essa informação" (no new prompt needed); FPR/recall-retention measured by the sweep
- [ ] `guardrails/adapters/reranker.py` behind a `Reranker` Protocol (adapter pattern); retrieve top-N≈20 → rerank top-3; `rerank_ms` in diagnostics/latency breakdown
- [ ] before/after table (dense-only vs +threshold vs +reranker) committed; **only positive-delta variant shipped**; loser documented as talking point
- [ ] Dense-only manual metrics reproduce `InformationRetrievalEvaluator` (anti-tautology check passes)
- [ ] `banking_kb` anti-regression gate passed before any `config.yaml` flip (≥ 0.9375 recall@5 / 0.8281 MRR)
- [ ] Unit tests pass (`-m "not slow"`); lint clean; heavy paths `@slow`
- [ ] ADR-006 + LIMITATIONS updated same change; doc numbers == run JSONs (no drift)
- [ ] (Stretch) Hybrid measured-or-deferred, deferral stated explicitly
