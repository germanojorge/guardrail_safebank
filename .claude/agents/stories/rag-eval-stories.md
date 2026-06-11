# RAG Hardening & Evaluation — Stories (SCRUM)

> Epic **[SCRUM-36]** · Project SCRUM ("Guardrail") · Source PRD: `.claude/agents/PRDs/PRD-rag-eval.md`
> Created in Jira 2026-06-11. Board: https://alumni-team-qit3uw2s.atlassian.net/jira/software/projects/SCRUM/board

## Dependency DAG
```
SCRUM-37 ──┬──▶ SCRUM-38 ──┐
           └──▶ SCRUM-39 ──┴──▶ SCRUM-40
```

---

## [SCRUM-37] Eval harness de retrieval + splits congelados + baseline
**Type:** Story · **Priority:** High · **Labels:** rag, evaluation · **Phase:** 1

As candidato, quero um harness reprodutível de retrieval, so that eu tenha um baseline quotável (recall@k / MRR / nDCG) e uma régua única para medir melhorias.

**AC**
- `scripts/eval_retrieval.py` emite recall@{1,3,5,10}, MRR@10, nDCG@10, MAP via `InformationRetrievalEvaluator`.
- Split `test` do `Itau-Unibanco/FAQ_BACEN` congelado em `data/eval/faq_bacen_eval.jsonl` (seeded, commitado), reusando `load_faq_data` (`scripts/finetune_itau_embedding.py:37`) — leakage-free declarado.
- Smoke set `data/eval/banking_kb_eval.jsonl` (~15 q) no mesmo harness, reportado à parte, marcado closed-loop.
- Baseline e5-small/384 salvo em `models/eval/<run>.json`.
- Flags `--model` / `--dataset`.

**Blocks:** SCRUM-38, SCRUM-39

---

## [SCRUM-38] Model bake-off — justificar modelo + dimensões por medição
**Type:** Story · **Priority:** High · **Labels:** rag, embeddings · **Phase:** 2

As candidato, quero comparar modelos na mesma métrica e split, so that eu justifique "por que esse modelo / por que 384 dims" com dados.

**AC**
- Bake-off: e5-small(384) vs e5-base(768) vs MiniLM-L12-v2(384) vs fine-tune existente, mesmo split congelado.
- Tabela modelo × dim × recall@5 × MRR@10 × nDCG@10 × latência/query(CPU).
- Vencedor shipado em `config.yaml` só após sanity-check anti-regressão no `banking_kb`.

**Blocked by:** SCRUM-37 · **Blocks:** SCRUM-40

---

## [SCRUM-39] Retrieval: score threshold + cross-encoder reranker (medidos)
**Type:** Story · **Priority:** High · **Labels:** rag, retrieval · **Phase:** 2–3

As atendente-bot bancário, quero não passar contexto irrelevante e re-ranquear candidatos, so that a qualidade suba e eu evite alucinar conselho financeiro.

**AC**
- Score threshold em `retrieve` (`guardrails/pipeline/nodes.py:92`)/`search` (`vector_store.py:97`): off-topic → "não tenho essa informação"; FPR medido.
- Cross-encoder reranker: `guardrails/adapters/reranker.py` atrás de Protocol; top-N → top-3; `rerank_ms` nos diagnostics.
- Tabela before/after; ship só delta positivo.
- (Stretch) Hybrid BM25+dense atrás de flag; senão talking point.

**Blocked by:** SCRUM-37 · **Blocks:** SCRUM-40

---

## [SCRUM-40] Documentação RAG — docs/RAG.md + interview notes + ADR/LIMITATIONS
**Type:** Task · **Priority:** High · **Labels:** rag, docs · **Phase:** 4

As reviewer / candidato, quero documentação auto-contida e reprodutível, so that eu defenda cada escolha sob grilling sem doc drift.

**AC**
- `docs/RAG.md`: bake-off, dims trade-off, chunking + alternativas rejeitadas, retrieval + deltas, eval methodology + leakage statement, comandos, racional Qdrant.
- `docs/RAG_interview_notes.md`: cheat-sheet Q&A das 5 perguntas + follow-ups.
- `adr/006-local-embeddings.md` com números medidos; `LIMITATIONS.md` com gaps confirmados.
- Números na doc == `models/eval/*.json`.

**Blocked by:** SCRUM-38, SCRUM-39
