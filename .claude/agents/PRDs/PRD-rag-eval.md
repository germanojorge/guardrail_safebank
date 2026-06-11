# PRD — RAG Hardening & Evaluation Harness

> **Sub-projeto** do guardrail-safebank. Foco: tornar o pipeline de RAG defensável sob escrutínio de especialista e fechar o furo central — **ausência de avaliação de retrieval end-to-end** (recall@k / MRR / nDCG). Motivado por entrevista técnica no Itaú focada em RAG e busca semântica.
>
> **Criado:** 2026-06-11 · **Alvo:** 2026-06-12 (1 dia) · Alinhado ao plano em `~/.claude/plans/d-uma-olhada-no-twinkling-trinket.md` e às regras de `building-rigorously.md`.

---

## 1. Executive Summary

O guardrail-safebank já tem um pipeline RAG funcional (LangGraph → embed → Qdrant cosine top-3 → Claude Sonnet), mas com um furo crítico de credibilidade: **não existe avaliação de retrieval sobre o que o sistema de fato serve.** Há apenas um CSV de avaliação de fine-tune, sem baseline comparável nem harness reprodutível. Um entrevistador focado em RAG desmonta isso em duas perguntas ("qual seu recall? como sabe que o reranker ajudou?").

Este PRD define a construção de um **harness de avaliação como espinha dorsal**: um conjunto golden congelado e fora-da-amostra (split `test` do `Itau-Unibanco/FAQ_BACEN` — dados reais, públicos, do próprio Itaú), métricas padrão de IR (recall@k, MRR@10, nDCG@10, MAP), e um caminho único pelo qual *toda* melhoria de retrieval passa para ser medida. Sobre essa espinha, melhorias (threshold de score, cross-encoder reranker, hybrid BM25+dense) só entram em produção se os números provarem ganho.

**Princípio central (de `building-rigorously.md`):** a avaliação é a espinha; toda "melhoria" é provada por um número, não afirmada. Evita-se deliberadamente o loop fechado de autorar query, documento, matcher e label no mesmo fluxo.

**Meta do MVP:** baseline reprodutível + tabela de bake-off de modelos + ao menos uma melhoria medida com delta assinado + documentação que sobrevive ao grilling de especialista.

---

## 2. Mission

Tornar cada decisão do RAG — modelo, dimensões, vector store, chunking, retrieval — **defensável por medição**, não por narrativa.

**Princípios:**
1. **Eval-first** — o harness é construído antes de qualquer feature; features são gated pelos números.
2. **Sem loop fechado** — métrica de manchete vem de dataset externo real com labels gratuitos; fixtures hand-crafted são marcadas como closed-loop em `LIMITATIONS.md`.
3. **Honestidade de limites** — gaps confirmados são documentados, não escondidos (anti "100% pass").
4. **Reprodutibilidade** — split congelado e commitado; números na doc batem com o JSON de eval (sem doc drift).
5. **Ship só o que ganha** — feature que não melhora vira talking point documentado, não código morto.

---

## 3. Target Users

| Persona | Comfort técnico | Necessidade / dor |
|---|---|---|
| **Candidato (você)** preparando entrevista | Alto | Defender cada decisão de RAG com número; ter cheat-sheet de Q&A; baseline quotável |
| **Entrevistador Itaú** (especialista RAG/semântica) | Muito alto | Verificar rigor: split held-out, leakage, escolha de modelo medida, estratégia de retrieval |
| **Reviewer / future-you** | Alto | Ler `docs/RAG.md` top-to-bottom e reproduzir os números com um comando |

---

## 4. MVP Scope

### In Scope

**Avaliação (Core)**
- [ ] Harness `scripts/eval_retrieval.py` com recall@{1,3,5,10}, MRR@10, nDCG@10, MAP
- [ ] Golden set congelado: split `test` do `FAQ_BACEN` → `data/eval/faq_bacen_eval.jsonl`
- [ ] Smoke set hand-crafted `banking_kb` (~15 q) → `data/eval/banking_kb_eval.jsonl`, marcado closed-loop
- [ ] Baseline reprodutível do modelo atual (e5-small/384)

**Modelos**
- [ ] Bake-off: e5-small (384) vs e5-base (768) vs MiniLM-L12-v2 (384) vs fine-tune existente
- [ ] Tabela quality × latência(CPU) × dimensões; ship do vencedor (com sanity-check anti-regressão no `banking_kb`)

**Retrieval**
- [ ] Threshold de score mínimo (cosine) — "não tenho essa informação" quando top-k é lixo
- [ ] Cross-encoder reranker (retrieve top-N → rerank top-3), medido, ship-se-ganhar

**Documentação**
- [ ] `docs/RAG.md` (rigoroso, auto-contido)
- [ ] `docs/RAG_interview_notes.md` (cheat-sheet Q&A)
- [ ] Update `adr/006-local-embeddings.md` com números medidos
- [ ] Append em `LIMITATIONS.md` (gaps confirmados)

### Out of Scope (Extras / talking points)
- [ ] Hybrid BM25+dense via sparse vectors do Qdrant — *implementar-se-sobrar-tempo*, senão talking point
- [ ] Query expansion / HyDE / multi-query
- [ ] Re-chunking (semantic / parent-document / small-to-big) — documentar alternativas, não construir
- [ ] Troca de vector DB — Qdrant fica
- [ ] Calibração de relevância contra labels humanos / Cohen's kappa
- [ ] Reask / groundedness judge sobre chunks RAG

---

## 5. User Stories

1. **Como candidato**, quero rodar um comando e obter recall@k/MRR/nDCG do modelo atual, para ter um baseline quotável.
   *Ex.: `uv run python scripts/eval_retrieval.py --model intfloat/multilingual-e5-small` → tabela markdown.*

2. **Como candidato**, quero uma tabela de bake-off de modelos na mesma métrica, para responder "por que esse modelo / por que 384 dims" com dados, não vibe.

3. **Como candidato**, quero medir o delta de um reranker, para dizer "dense-only MRR=X, +reranker=Y" e mostrar o script que prova.

4. **Como entrevistador**, quero confirmar que as queries de eval nunca tocaram o treino, para confiar nos números do fine-tune.
   *Ex.: declaração de leakage + split commitado verificável.*

5. **Como reviewer**, quero ler `docs/RAG.md` e reproduzir cada número, para confiar que a doc não tem drift.

6. **Como atendente-bot em produção**, quero não responder com contexto irrelevante, para evitar alucinar conselho financeiro.
   *Ex.: query off-topic → threshold corta → "não tenho essa informação".*

7. **(Técnica) Como dev**, quero um único caminho de métrica parametrizável (`--model/--reranker/--hybrid/--threshold`), para que toda config passe pela mesma régua.

---

## 6. Core Architecture & Patterns

**Abordagem:** harness de eval externo e auto-contido + melhorias plugáveis atrás de flags nos adapters/nodes existentes. Reuso máximo do que já existe.

```
scripts/eval_retrieval.py
   ├─ reusa load_faq_data()  (scripts/finetune_itau_embedding.py:37)  → mesma lógica de split (garante leakage-free)
   ├─ congela → data/eval/faq_bacen_eval.jsonl  (seeded, commitado)
   ├─ InformationRetrievalEvaluator (sentence_transformers)  → recall@k, MRR, nDCG, MAP
   └─ --model / --reranker / --threshold / --hybrid  → caminho único de métrica
        → models/eval/<run>.json + tabela markdown

Produção (gated pelos números):
   guardrails/pipeline/nodes.py::retrieve   → + threshold, + rerank opcional
   guardrails/adapters/vector_store.py::search → + top-N / threshold
   guardrails/adapters/reranker.py (novo, atrás de Protocol)
   config.yaml → bloco retrieval
```

**Padrões-chave:**
- **Reuso de split** — `load_faq_data` para herdar a garantia anti-leakage (treino só no split `train`, queries do `test`).
- **Protocol/adapter** — reranker segue o padrão de `EmbeddingProvider`/`VectorStore` (DI via `_create_components` em `guardrails/api/app.py:27`).
- **Gate por medição** — feature só é wired em produção se a linha before/after da tabela mostrar ganho.
- **Congelamento determinístico** — eval set seeded e commitado para reprodutibilidade.

---

## 7. Tools/Features

### F-1 — Eval Harness (`scripts/eval_retrieval.py`)
- **Propósito:** régua única de retrieval.
- **Operações:** load split → freeze JSONL → embed corpus/queries → `InformationRetrievalEvaluator` → emit recall@{1,3,5,10}, MRR@10, nDCG@10, MAP → tabela markdown + `models/eval/<run>.json`.
- **Flags:** `--model`, `--reranker`, `--hybrid`, `--threshold`, `--dataset {faq_bacen,banking_kb}`.

### F-2 — Model Bake-off
- **Propósito:** justificar modelo + dimensões por medição.
- **Saída:** tabela `modelo × dim × recall@5 × MRR@10 × nDCG@10 × latência/query(CPU)`.
- **Regra:** ship do vencedor; sanity-check anti-regressão no `banking_kb` antes de trocar `config.yaml`.

### F-3 — Score Threshold
- **Propósito:** segurança — não passar contexto lixo ao LLM.
- **Onde:** `nodes.py::retrieve` / `vector_store.py::search`. Mede FPR/qualidade.

### F-4 — Cross-encoder Reranker
- **Propósito:** maior alavanca medível de qualidade.
- **Como:** retrieve top-N(~20) → rerank top-3 com cross-encoder multilíngue (ex.: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`). Novo `guardrails/adapters/reranker.py`. Ship-se-ganhar.

### F-5 — Hybrid BM25+dense (if time)
- **Propósito:** termos exatos bancários (CDB, IOF, números de conta, siglas).
- **Como:** sparse vectors nativos do Qdrant atrás de flag. Mede; ship-se-ganhar; senão talking point.

### F-6 — Documentação
- `docs/RAG.md`, `docs/RAG_interview_notes.md`, update ADR-006, append `LIMITATIONS.md`.

---

## 8. Technology Stack

- **Embeddings:** sentence-transformers — `intfloat/multilingual-e5-small` (atual), candidatos `multilingual-e5-base`, `paraphrase-multilingual-MiniLM-L12-v2`, fine-tune local
- **Eval:** `sentence_transformers.evaluation.InformationRetrievalEvaluator`; `datasets` (HF) para `Itau-Unibanco/FAQ_BACEN`
- **Reranker:** cross-encoder multilíngue (sentence-transformers `CrossEncoder`)
- **Vector store:** Qdrant (cosine; sparse vectors p/ hybrid)
- **Orquestração:** LangGraph (existente)
- **LLM:** Claude Sonnet 4.6 (chatbot) — inalterado
- **Runtime:** Python, `uv`, CPU-only; caches HF redirecionados via `guardrails.env_bootstrap`

---

## 9. Security & Configuration

- **Config:** novo bloco `retrieval` em `config.yaml` (`top_n`, `score_threshold`, `reranker.enabled`, `reranker.model`, `hybrid.enabled`). Overrides por env mantêm padrão existente (`QDRANT_*`).
- **Sem credenciais novas** — datasets HF públicos; modelos locais. `ANTHROPIC_API_KEY` inalterado.
- **Anti-leakage (segurança de avaliação):** garantir que queries de eval ∉ treino; declarar explicitamente em `docs/RAG.md`.
- **Out of scope:** auth, deploy AWS, mudanças no guardrail de segurança.

---

## 10. API Specification

Sem novos endpoints. Mudança comportamental em `POST /chat`:
- Com **threshold** ativo, query sem chunk acima do corte → resposta "não tenho essa informação / fale com um gerente" (via `CHATBOT_SYSTEM_PROMPT`), sem contexto alucinado.
- Com **reranker** ativo, diagnostics ganham `rerank_ms` no breakdown de latência (visível em `docker logs ... | jq`).

CLI nova:
```bash
uv run python scripts/eval_retrieval.py --model <hf_id> [--reranker <hf_id>] [--threshold 0.x] [--dataset faq_bacen]
```

---

## 11. Success Criteria

**MVP é sucesso se:** existe um baseline reprodutível + tabela de bake-off + ≥1 melhoria com delta assinado, tudo commitado e batendo com a doc.

- [ ] `eval_retrieval.py --model e5-small` produz baseline (recall@k/MRR@10/nDCG@10) no split `test` congelado
- [ ] Tabela de bake-off reprodutível a partir do eval set commitado
- [ ] Threshold e/ou reranker mostram delta assinado vs baseline (vencedor shipado; perdedor documentado)
- [ ] Smoke `banking_kb` roda no mesmo harness, reportado à parte e marcado closed-loop
- [ ] Declaração de leakage verificável (split commitado)
- [ ] Números de `docs/RAG.md` == `models/eval/*.json` (sem doc drift)
- [ ] `docs/RAG_interview_notes.md` cobre as 5 perguntas + follow-ups (hybrid/reranking/chunking/eval)

**Qualidade:** green-on-first-try é tratado como aviso, não vitória (§3 building-rigorously) — comparar com SOTA publicado.

---

## 12. Implementation Phases

### Fase 1 — Harness + Baseline (não-negociável)
- **Meta:** régua única + baseline quotável.
- **Entregáveis:** [ ] `scripts/eval_retrieval.py` · [ ] `data/eval/faq_bacen_eval.jsonl` congelado · [ ] baseline e5-small
- **Validação:** comando roda, emite tabela, JSON commitado; leakage declarado.

### Fase 2 — Bake-off + Threshold
- **Meta:** justificar modelo/dims por medição; segurança de contexto.
- **Entregáveis:** [ ] tabela 4-modelos com latência · [ ] threshold em `retrieve` · [ ] sanity-check `banking_kb`
- **Validação:** vencedor identificado; off-topic → "não tenho essa informação".

### Fase 3 — Reranker (+ Hybrid se sobrar)
- **Meta:** maior alavanca de qualidade, medida.
- **Entregáveis:** [ ] `guardrails/adapters/reranker.py` · [ ] linha before/after na tabela · [ ] hybrid atrás de flag (if time)
- **Validação:** delta assinado; ship só se ganhar; `rerank_ms` nos diagnostics.

### Fase 4 — Documentação
- **Meta:** sobreviver ao grilling.
- **Entregáveis:** [ ] `docs/RAG.md` · [ ] `docs/RAG_interview_notes.md` · [ ] ADR-006 update · [ ] `LIMITATIONS.md`
- **Validação:** números batem com JSON; cheat-sheet cobre as 5 perguntas. *(Pode rodar em paralelo: narrativa de chunking/vector DB não depende dos números.)*

**Ordem se faltar tempo:** harness+baseline+bake-off → threshold → reranker → hybrid → polish de doc.

---

## 13. Future Considerations

- Hybrid search shipado como feature de manchete (sparse vectors Qdrant)
- Query expansion / HyDE / multi-query retrieval
- Re-chunking semântico / parent-document (small-to-big)
- Groundedness judge com claim decomposition contra chunks
- Voyage AI embeddings (qualidade PT-BR superior) — trade-off já em ADR-006
- Calibração de relevância contra labels humanos (Cohen's kappa)
- Migração AWS (OpenSearch como vector store, Titan/Cohere embeddings)

---

## 14. Risks & Mitigations

| Risco | Mitigação |
|---|---|
| **Over-scope na véspera** — tentar shipar tudo e não fechar nada | Ordem de prioridade estrita; harness+baseline é o mínimo entregável; features são gated e opcionais |
| **Loop fechado disfarçado** — manchete em corpus sintético autorado | Manchete só do `FAQ_BACEN` (labels externos); `banking_kb` marcado closed-loop em `LIMITATIONS.md` |
| **Acusação de leakage** — eval no dataset de fine-tune | Reusar `load_faq_data` (treino só `train`, queries `test`); commitar split; declarar na doc |
| **Fine-tune overfit ao FAQ** — regride no `banking_kb` da demo | Sanity-check anti-regressão antes de trocar `config.yaml`; ship só se não regredir a demo |
| **Doc drift** — números na doc divergem do código | Números de `docs/RAG.md` gerados/copiados do `models/eval/*.json`; atualizar no mesmo commit |
| **Feature sem ganho shipada às cegas** | Gate por before/after; perdedor vira talking point, não código |

---

## 15. Appendix

**Documentos relacionados**
- Plano: `~/.claude/plans/d-uma-olhada-no-twinkling-trinket.md`
- PRD do projeto: `.claude/agents/PRDs/PRD.md`
- Regras: `.claude/rules/building-rigorously.md` (§1 loop fechado, §3 green-on-first-try, §4 doc drift, §7 limites)
- ADR: `adr/006-local-embeddings.md`
- Sprint anterior: `.claude/agents/plans/sprint-eval-baseline.plan.md`

**Reuso de código existente**
- `scripts/finetune_itau_embedding.py:37` (`load_faq_data`), `:104` (`InformationRetrievalEvaluator`)
- `scripts/ingest_itau_faq.py` (split/campos do `FAQ_BACEN`)
- `guardrails/pipeline/nodes.py:92` (`retrieve`, `RETRIEVE_TOP_K`)
- `guardrails/adapters/vector_store.py:97` (`search`)
- `guardrails/api/app.py:27` (`_create_components` — DI)

**Dataset**
- `Itau-Unibanco/FAQ_BACEN` (HF Hub, público) — splits `train`/`test`
