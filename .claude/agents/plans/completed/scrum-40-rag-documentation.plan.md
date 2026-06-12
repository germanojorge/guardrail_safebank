# Plan: SCRUM-40 — Documentação RAG (docs/RAG.md + interview notes + ADR/LIMITATIONS)

## Summary

Produce self-contained, reproducible documentation of every RAG decision so each choice survives expert grilling **without doc drift**. This is a documentation-only task (no production code changes). Two new docs are authored (`docs/RAG.md`, `docs/RAG_interview_notes.md`) and two existing docs are reconciled against the shipped config and the measured eval JSONs (`adr/006-local-embeddings.md`, `LIMITATIONS.md`). Every quantitative claim must trace back to a file under `models/eval/` — this is the load-bearing acceptance criterion (building-rigorously §4).

## User Story

As a reviewer / candidate
I want self-contained, reproducible documentation of the RAG decisions
So that I can defend every choice under expert grilling without doc drift.

## Metadata

| Field | Value |
|-------|-------|
| Type | DOCUMENTATION |
| Complexity | MEDIUM |
| Systems Affected | `docs/` (new), `adr/006`, `LIMITATIONS.md` |
| Jira Issue | SCRUM-40 (parent epic SCRUM-36; blocked-by SCRUM-38, SCRUM-39 — both now committed) |

---

## Source-of-Truth Numbers (the only numbers allowed in the docs)

Every figure below is copied verbatim from a committed artifact. **Do not invent, round differently, or re-derive.** If a doc needs a number not here, stop and re-measure — do not guess.

### Embedding bake-off — `models/eval/bakeoff_faq_bacen_summary.json` + `bakeoff_faq_bacen.md`

faq_bacen (373 queries, 1678 corpus docs):

| Model | dim | prefix | recall@1 | recall@3 | recall@5 | MRR@10 | nDCG@10 | latency ms/q |
|-------|-----|--------|----------|----------|----------|--------|---------|--------------|
| e5-small (prev) | 384 | e5 | 0.4316 | 0.6086 | 0.6836 | 0.5354 | 0.5891 | 22.7 |
| **e5-base (shipped)** | 768 | e5 | 0.4826 | 0.6756 | **0.7480** | 0.5885 | 0.6390 | 55.2 |
| MiniLM-L12-v2 | 384 | none | 0.2735 | 0.4424 | 0.4960 | 0.3718 | 0.4222 | 22.3 |
| itau-finetuned | 384 | none | SKIPPED (corrupted safetensors header) | | | | | |

banking_kb anti-regression gate (from SCRUM-38 report): e5-small recall@5 **0.875** / MRR@10 0.8125 → e5-base recall@5 **0.9375** / MRR@10 0.8281 (+6.25pp recall, gate PASSES).

### Retrieval before/after — `models/eval/retrieval_before_after.md`

Anti-tautology gate: `run_eval_manual` dense-only recall@3 = **0.6756** == `InformationRetrievalEvaluator` recall@3 = **0.6756**.

| Configuration | recall@3 | recall@5 | mrr@10 | ndcg@10 |
|---------------|----------|----------|--------|---------|
| Dense only (e5-base, top-3) | 0.6756 | 0.6756 | 0.5648 | 0.5932 |
| Dense-20 + CE reranker (top-3) | **0.6836** | 0.7426 | **0.6230** | **0.6668** |

Delta: +1.2pp recall@3 / +10.3pp mrr@10 / +12.4pp ndcg@10. recall@10 with reranker = 0.8043. CE model `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`.

### Threshold sweep — `models/eval/retrieval_before_after.md`

| threshold | recall@3 | off-topic rejection % |
|-----------|----------|------------------------|
| 0.70–0.76 | 0.6756 | 0.0% |
| 0.78 | 0.6756 | 10.0% |
| 0.80 | 0.6756 | 25.0% |
| **0.82 (selected)** | **0.6756** | **65.0%** |
| 0.84 | 0.6729 | 100.0% |
| 0.86 | 0.6139 | 100.0% |
| 0.88 | 0.4263 | 100.0% (recall cliff) |
| 0.90 | 0.1475 | 100.0% |
| 0.92 | 0.0268 | 100.0% |

### Shipped config — `config.yaml`

`embedding.model: intfloat/multilingual-e5-base` · `retrieval.top_k: 3` · `top_n: 20` · `score_threshold: 0.82` · `reranker.enabled: true` · `reranker.model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`.

---

## Ground-Truth Facts (chunking / vector store / methodology — read from code, not memory)

| Fact | Source |
|------|--------|
| **banking_kb chunking**: markdown split by blank-line paragraphs (`text.split("\n\n")`), heading-only paragraphs dropped; `chunk_idx` metadata per chunk; 8 PT-BR docs | `scripts/ingest_banking_kb.py:27-67` (`_split_paragraphs`) |
| **faq_bacen**: frozen FAQ_BACEN HF dataset → deterministic JSONL snapshots in `data/eval/` (corpus + eval), Q/A pairs; eval split is independent of corpus | `scripts/eval_retrieval.py:53-115` (`freeze_faq_bacen`, `_load_dataset`) |
| **Embedding prefixes**: E5 convention `query:` / `passage:` hidden in adapter; `apply_prefixes` helper, `prefix_style` param | `guardrails/adapters/embedding.py`, `scripts/eval_retrieval.py` (`apply_prefixes`) |
| **Vector store**: Qdrant, cosine, collection `banking_kb`, `score_threshold` param on `search` | `guardrails/adapters/vector_store.py`, `config.yaml` qdrant block |
| **Retrieve node order**: encode query → Qdrant cosine (top_n=20) → score_threshold filter → CE reranker → slice top_k=3 → LLM | `guardrails/pipeline/nodes.py` (`build_nodes`) |
| **Reranker adapters**: `Reranker` Protocol + `CrossEncoderReranker` + `IdentityReranker` | `guardrails/adapters/reranker.py` |
| **Metrics emitted**: recall@{1,3,5,10}, MRR@10, nDCG@10, MAP@10 | `scripts/eval_retrieval.py:580+` (`main`) |
| **Re-ingest caveat**: 384→768 dim requires dropping/recreating the Qdrant collection | SCRUM-38 report "Important Follow-up" |

---

## Reproducible Commands (verify each runs before putting it in a doc)

```bash
# env (heavy-model caches redirected via .env)
set -a; source .env; set +a

# Freeze FAQ_BACEN splits (network, run once)
uv run python scripts/eval_retrieval.py --freeze

# Bake-off across 4 models → models/eval/bakeoff_faq_bacen.md
uv run python scripts/bakeoff_embeddings.py --dataset faq_bacen

# Single-model eval (e5-base default), with reranker / threshold flags
uv run python scripts/eval_retrieval.py --dataset faq_bacen
uv run python scripts/eval_retrieval.py --dataset banking_kb   # anti-regression smoke

# Re-ingest after a dim change
docker compose run --rm ingest
```

> Note: confirm exact flag names for reranker/threshold sweep by reading `scripts/eval_retrieval.py` `main()` argparse block before documenting them — do not assume.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docs/RAG.md` | CREATE | Full RAG decision record: bake-off table, dimension trade-off, chunking rationale + rejected alternatives, retrieval strategy + deltas, eval methodology + leakage declaration, reproducible commands, Qdrant rationale |
| `docs/RAG_interview_notes.md` | CREATE | Q&A cheat-sheet for the 5 core questions + follow-ups (hybrid/reranking/eval) |
| `adr/006-local-embeddings.md` | UPDATE | Reconcile drift: shipped defaults are `score_threshold: 0.82` / `reranker.enabled: true` (ADR table currently shows them disabled); add final measured deltas |
| `LIMITATIONS.md` | UPDATE | Add confirmed RAG gaps the AC names explicitly: synthetic closed-loop corpus, ingest/eval mismatch, small corpus, cut features (BM25/hybrid) |

No code, tests, or config change. No commit until the user approves (per CLAUDE.md Git Workflow).

---

## Tasks

Execute in order. Tasks 1–2 (narrative) are independent of the numbers; Task 0 must precede any table.

### Task 0: Verify every source number is still current

- **Action**: READ-ONLY
- **Implement**: Re-open `models/eval/bakeoff_faq_bacen_summary.json`, `models/eval/retrieval_before_after.md`, `config.yaml`. Confirm the Source-of-Truth tables above match byte-for-byte. If any drift exists between this plan and the artifacts, the artifacts win — update the plan section first.
- **Validate**: numbers in the plan == numbers in the JSON/md.

### Task 1: `docs/RAG.md` — narrative sections (number-free)

- **File**: `docs/RAG.md`
- **Action**: CREATE
- **Implement** sections that do NOT depend on measured numbers:
  - **Chunking strategy**: blank-line paragraph splitting for banking_kb (cite `_split_paragraphs`), why; **rejected alternatives** with one-line reasons each: fixed-size + overlap, semantic chunking, parent-document / small-to-big.
  - **Vector store rationale (Qdrant)**: open-source, native metadata filters, docker-compose fit, simple API behind adapter, cosine — cross-link ADR-002/006.
  - **Eval methodology + leakage declaration**: two datasets (faq_bacen frozen HF split = external-ish; banking_kb = synthetic closed-loop anti-regression gate); anti-tautology gate (manual vs InformationRetrievalEvaluator); **explicit leakage statement** that banking_kb corpus and its eval queries share an author (closed loop, building-rigorously §1).
  - **Reproducible commands** block (from section above, flag names verified).
- **Mirror**: tone/structure of `adr/006-local-embeddings.md` and `LIMITATIONS.md` (PT/EN mix, tables, terse).
- **Validate**: `ls docs/RAG.md`; no numeric claims yet.

### Task 2: `docs/RAG.md` — measured tables

- **File**: `docs/RAG.md`
- **Action**: UPDATE
- **Implement**: paste the three Source-of-Truth tables (bake-off, reranker before/after, threshold sweep) + dimension trade-off paragraph (768-dim e5-base: +9.4pp recall@5 on faq_bacen / +6.25pp on banking_kb vs +300MB weight + ~32ms/q latency). Add retrieval-strategy section stating shipped deltas: threshold 0.82 (65% off-topic rejection, 0 recall cost), reranker enabled (+1.2pp recall@3, +10.3pp mrr, +12.4pp ndcg). Each table footnoted with its source JSON/md filename.
- **Validate**: every number traces to `models/eval/*` — diff visually against Source-of-Truth tables.

### Task 3: `docs/RAG_interview_notes.md` — Q&A cheat-sheet

- **File**: `docs/RAG_interview_notes.md`
- **Action**: CREATE
- **Implement**: tight Q&A for the 5 core questions — (1) why e5-base, (2) why 768 dims, (3) why Qdrant, (4) which chunking, (5) which retrieval — each answer one short paragraph + the killer number. Then follow-ups: hybrid (BM25 + dense — why deferred), reranking (already shipped, the deltas), eval (leakage honesty, anti-tautology gate). Each answer cross-links the deeper section in `docs/RAG.md`.
- **Validate**: every claim is a pointer into RAG.md or a Source-of-Truth number.

### Task 4: `adr/006-local-embeddings.md` — fix drift

- **File**: `adr/006-local-embeddings.md`
- **Action**: UPDATE
- **Implement**: The "Retrieval post-processing" table (lines ~28-34) lists defaults as `score_threshold: null (disabled)` / `reranker.enabled: false`, but **`config.yaml` ships 0.82 / true**. Reconcile: show the shipped values and note the gating mechanism kept the flags but measurement turned them on. Add the measured deltas inline (they currently point only to the before/after file). Keep the AC literal: "atualizado com os números medidos (que faltavam)."
- **Validate**: ADR table values == `config.yaml` values.

### Task 5: `LIMITATIONS.md` — confirmed RAG gaps the AC names

- **File**: `LIMITATIONS.md`
- **Action**: UPDATE
- **Implement**: Retrieval section already has multi-hop, groundedness, in-memory-vs-Qdrant. Add the three the AC explicitly names and that are missing/implicit:
  - **Synthetic closed-loop corpus**: banking_kb's 8 docs and their eval queries authored by the same agent — measures pattern coverage, not real-world recall (building-rigorously §1).
  - **Small corpus**: 8 banking_kb docs / faq_bacen is a public FAQ, not this bank's production KB — absolute recall numbers won't transfer.
  - **Cut features**: hybrid retrieval (BM25 + dense fusion) not implemented; dense-only misses exact-keyword / out-of-vocabulary terms (account numbers, product codes).
  - Promote/cross-ref the existing "in-memory eval vs Qdrant" as the **ingest/eval mismatch** the AC names.
- **Validate**: each of the four AC-named gaps appears once, no duplication of existing rows.

### Task 6: Cross-doc consistency sweep

- **Action**: READ-ONLY
- **Implement**: grep the four docs for every numeric token and confirm each matches Source-of-Truth. Confirm `docs/RAG.md` ↔ ADR-006 ↔ LIMITATIONS tell one story. Confirm README's RAG/embeddings rows aren't newly contradicted (e5-base, reranker, threshold).
- **Validate**: `grep -rEn '0\.[0-9]{3,4}|[0-9]+pp|768|384|0\.82|0\.84' docs/ adr/006-local-embeddings.md` — eyeball every hit against the JSON.

---

## Validation

```bash
# Numbers cross-check — every metric token must trace to models/eval/*
grep -rEn '0\.[0-9]{3,4}|[0-9]+\.?[0-9]*pp|0\.82|0\.84|768|420MB|300MB' docs/ adr/006-local-embeddings.md LIMITATIONS.md

# Config ↔ ADR drift check (must agree)
grep -E 'score_threshold|reranker|e5-base|top_k|top_n' config.yaml
grep -E 'score_threshold|reranker|e5-base|0.82' adr/006-local-embeddings.md

# Docs render / links resolve (manual eyeball)
ls -la docs/RAG.md docs/RAG_interview_notes.md

# Markdown lint if pre-commit covers it
pre-commit run --files docs/RAG.md docs/RAG_interview_notes.md adr/006-local-embeddings.md LIMITATIONS.md || true
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| **Doc drift** — a number in the docs diverges from `models/eval/*` (the one AC that fails the whole ticket) | Task 0 freezes Source-of-Truth tables; Task 6 greps every numeric token back to JSON. Artifacts always win over memory. |
| **ADR-006 already-stale** — table shows disabled defaults but config ships enabled | Task 4 explicitly reconciles; flagged as confirmed drift, not a new doc. |
| **Inventing a "clean knee"** in the threshold story | Source data says *no clean knee* (rejection starts 0.78, 100% at 0.84). Quote that verbatim — the honesty is the senior signal (building-rigorously §7). |
| **Hand-waving chunking alternatives** | Each rejected alternative gets a concrete one-line reason tied to this corpus (short FAQ-style docs), not generic textbook prose. |
| **Over-claiming reranker win** | +1.2pp recall@3 is small; lead with the larger mrr/ndcg gains and state the recall delta plainly. |

---

## Acceptance Criteria (mirrors Jira)

- [ ] `docs/RAG.md`: bake-off table, dimension trade-off, chunking rationale + rejected alternatives (fixed-size+overlap, semantic, parent-document/small-to-big), retrieval strategy + deltas (threshold/reranker/hybrid), eval methodology + **leakage declaration**, reproducible commands, Qdrant rationale.
- [ ] `docs/RAG_interview_notes.md`: cheat-sheet Q&A for the 5 questions + follow-ups (hybrid/reranking/eval).
- [ ] `adr/006-local-embeddings.md` updated with the measured numbers (and shipped-config drift fixed).
- [ ] `LIMITATIONS.md` with confirmed gaps: synthetic closed-loop corpus, ingest/eval mismatch, small corpus, cut features.
- [ ] Numbers in `docs/RAG.md` **match** `models/eval/*.json` (no doc drift, building-rigorously §4).
- [ ] No code/config/test changes; nothing committed until user approves.
