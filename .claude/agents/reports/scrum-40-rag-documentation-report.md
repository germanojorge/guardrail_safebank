# Implementation Report

**Plan**: `.claude/agents/plans/scrum-40-rag-documentation.plan.md`
**Branch**: `main`
**Status**: COMPLETE

## Summary

Documentation-only task. Produced two new docs (`docs/RAG.md`, `docs/RAG_interview_notes.md`) and reconciled two existing docs (`adr/006-local-embeddings.md`, `LIMITATIONS.md`) against shipped config and measured eval JSONs. Every numeric claim in the new docs traces to `models/eval/` artifacts.

One drift found and corrected: ADR-006 had `+9.4pp recall@5 on faq_bacen` — the actual delta per `bakeoff_faq_bacen_summary.json` is `+6.4pp` (0.7480 − 0.6836 = 0.0644). Corrected in ADR-006 and used correct value in all new docs.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Verify source-of-truth numbers | `models/eval/*.json`, `config.yaml` | ✅ |
| 1 | `docs/RAG.md` — narrative sections | `docs/RAG.md` | ✅ |
| 2 | `docs/RAG.md` — measured tables | `docs/RAG.md` | ✅ |
| 3 | `docs/RAG_interview_notes.md` | `docs/RAG_interview_notes.md` | ✅ |
| 4 | `adr/006-local-embeddings.md` — fix drift | `adr/006-local-embeddings.md` | ✅ |
| 5 | `LIMITATIONS.md` — confirmed RAG gaps | `LIMITATIONS.md` | ✅ |
| 6 | Cross-doc consistency sweep | all four docs | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Pre-commit (ruff) | ✅ Skipped (markdown only) |
| Config ↔ ADR-006 agreement | ✅ Both show `score_threshold: 0.82`, `reranker.enabled: true` |
| Numeric grep vs source JSONs | ✅ All metric tokens trace to `models/eval/` |
| `docs/RAG.md` file exists | ✅ 9.9KB |
| `docs/RAG_interview_notes.md` file exists | ✅ 5.9KB |

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `docs/RAG.md` | CREATE | Full RAG decision record: bake-off, dimension trade-off, chunking + rejected alternatives, retrieval strategy, threshold sweep, eval methodology + leakage declaration, reproducible commands |
| `docs/RAG_interview_notes.md` | CREATE | Q&A cheat-sheet for 5 core questions + hybrid/reranking/eval follow-ups |
| `adr/006-local-embeddings.md` | UPDATE | Fixed `+9.4pp` → `+6.4pp` typo; updated score_threshold/reranker defaults from `null/false` to `0.82/true` with measured deltas |
| `LIMITATIONS.md` | UPDATE | Added 4 confirmed RAG gaps: synthetic closed-loop corpus, small corpus, ingest/eval mismatch, cut features (BM25/hybrid) |

## Deviations from Plan

**ADR-006 extra fix**: Plan Task 4 targeted only the score_threshold/reranker defaults drift. During Task 0 verification, I found the `+9.4pp` claim in ADR-006 does not match `bakeoff_faq_bacen_summary.json` (actual: `+6.4pp`). Corrected in the same pass per building-rigorously §4 (doc drift is lying — fix in the same change).

## Tests Written

None — documentation-only task. No code was written or modified.
