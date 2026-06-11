# Plan: SCRUM-37 — Eval harness de retrieval + splits congelados + baseline

> **Criado:** 2026-06-11 · **Status:** planejado · **Epic:** SCRUM-36 (RAG Hardening & Evaluation)
> **Origem:** `.claude/agents/PRDs/PRD-rag-eval.md` (Fase 1) · stories `.claude/agents/stories/rag-eval-stories.md`
> **Foco único:** a **régua**. Esta story constrói só o harness + os splits congelados + o baseline e5-small. Bake-off (SCRUM-38), threshold/reranker (SCRUM-39) e docs (SCRUM-40) são stories separadas e **não** entram aqui — mas o harness é projetado para elas plugarem via flags.

---

## Summary

Construir `scripts/eval_retrieval.py`: um harness de avaliação de retrieval **auto-contido e reprodutível** que lê splits **congelados e commitados** (não baixa da rede no momento do eval), aplica os prefixos E5 corretamente, roda `InformationRetrievalEvaluator` (sentence-transformers 5.5.1) e emite recall@{1,3,5,10}, MRR@10, nDCG@10, MAP — como tabela markdown no stdout **e** como `models/eval/<run>.json`. O conjunto golden de manchete vem do split `test` real do `Itau-Unibanco/FAQ_BACEN` (labels externos, leakage-free por construção); um smoke set hand-crafted `banking_kb` (~15 q) roda no mesmo harness, reportado à parte e **marcado closed-loop**. Entregável: baseline e5-small/384 quotável.

## User Story

As candidato
I want um harness reprodutível que rode um comando e cuspa recall@k / MRR / nDCG do modelo atual sobre dados externos não-vazados
So that eu tenha um baseline quotável e uma régua única por onde toda melhoria de retrieval passa.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `scripts/`, `data/eval/`, `models/eval/`, (read-only) adapters de embedding |
| Jira Issue | SCRUM-37 |
| Blocks | SCRUM-38 (bake-off), SCRUM-39 (threshold/reranker) |
| Depende de | nada (raiz do DAG) |

---

## Decisões de design travadas (pra sobreviver ao grilling)

| # | Decisão | Por quê |
|---|---|---|
| D1 | **Splits congelados em JSONL commitado; eval lê do disco, não da rede** | Reprodutibilidade total (§4 building-rigorously: doc não pode driftar do código). Um flag `--freeze` regenera do HF; o eval normal nunca baixa. |
| D2 | **Layout estilo BEIR: `corpus.jsonl` + `eval.jsonl` (queries+qrels embutidos)** | Convenção da indústria (BEIR/MTEB usam corpus/queries/qrels). Defensável: "seguimos o layout BEIR". O AC nomeia `faq_bacen_eval.jsonl`; o corpus companion `faq_bacen_corpus.jsonl` é escolha documentada. |
| D3 | **Prefixos E5 aplicados bakeando `"query: "`/`"passage: "` nos valores dos dicts** do evaluator (preservando os doc_ids) | `InformationRetrievalEvaluator` v5 **não** expõe param de prompt confiável; bakear no texto é version-proof e espelha exatamente `SentenceTransformerProvider` (`embedding.py:63-71`). |
| D4 | **⚠️ Rigor note:** `finetune_itau_embedding.py:104` roda o evaluator **SEM** prefixos E5 → sub-mede e5 ~20-30% | Nosso harness corrige isso. **Não comparar** nossos números com o `models/itau-embedding-eval/` antigo às cegas — é maçã com laranja. Anotar no JSON do run (`prefixes_applied: true`) e citar em SCRUM-40. |
| D5 | **Reusar a lógica de split de `load_faq_data`** (corpus = answers train+test; queries = só `test`; gold = `test_{i}`) | Herda a garantia anti-leakage: treino do fine-tune só viu `train`; queries de eval vêm de `test`. Answers de `train` ficam como **distractors** no corpus (torna a métrica mais honesta, não menos). |
| D6 | **`banking_kb` é closed-loop DECLARADO**: corpus derivado de `data/banking_kb/*.md` (reusa `_split_paragraphs`), queries hand-crafted | §1 building-rigorously: o autor das queries é o mesmo do corpus → tautológico. Reportado à parte, marcado `closed_loop: true` no JSON, e em `LIMITATIONS.md` (SCRUM-40). Serve de sanity/anti-regressão, **nunca** de manchete. |
| D7 | **Determinismo:** ordenação estável dos doc_ids; `seed` fixo; floats no JSON com precisão fixa | Rerun produz byte-idêntico → diff vazio confirma reprodutibilidade. |

---

## Patterns to Follow

### Bootstrap de ambiente (PRIMEIRA linha, antes de importar datasets/transformers)
```python
# SOURCE: scripts/finetune_itau_embedding.py:17 e scripts/ingest_itau_faq.py:16
import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de datasets/transformers
```

### Lógica de split leakage-free a reusar (NÃO reimplementar)
```python
# SOURCE: scripts/finetune_itau_embedding.py:37-82  (load_faq_data)
# corpus = {f"train_{i}": ans} ∪ {f"test_{i}": ans}   (train = distractors)
# queries = test questions ; relevant_docs[query_text] = {f"test_{i}"}
```

### Prefixos E5 (espelhar — mesma convenção do provider)
```python
# SOURCE: guardrails/adapters/embedding.py:63-71
def embed_queries(...):  return self._encode([f"query: {t}" for t in texts])
def embed_passages(...): return self._encode([f"passage: {t}" for t in texts])
# No harness: corpus[doc_id] = "passage: " + ans ; queries[qid] = "query: " + q
```

### InformationRetrievalEvaluator (API v5.5.1 confirmada via context7)
```python
# keys de saída: f"{name}_cosine_recall@{k}", f"{name}_cosine_mrr@{k}",
#                f"{name}_cosine_ndcg@{k}", f"{name}_cosine_map@{k}"
from sentence_transformers.evaluation import InformationRetrievalEvaluator
ev = InformationRetrievalEvaluator(
    queries=queries, corpus=corpus, relevant_docs=relevant_docs, name="faq_bacen",
    accuracy_at_k=[1,3,5,10], precision_recall_at_k=[1,3,5,10],
    mrr_at_k=[10], ndcg_at_k=[10], map_at_k=[10],
    show_progress_bar=True,
)
results = ev(model)  # dict[str, float]
```

### CLI / argparse + estrutura de script
```python
# SOURCE: scripts/finetune_itau_embedding.py:182-205  (argparse + main + raise SystemExit)
```

### Teste com mock de SentenceTransformer (sem download)
```python
# SOURCE: tests/unit/test_embedding.py:19-28  (MagicMock encode → np.zeros)
# marca @pytest.mark.slow / network nos testes que baixam modelo/dataset real
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/_faq_data.py` | CREATE | Módulo compartilhado: `load_faq_data` (+ `build_evaluator`) extraído do fine-tune. Evita import de script com `__main__` (R3). |
| `scripts/finetune_itau_embedding.py` | UPDATE | Importar `load_faq_data`/`build_evaluator` de `_faq_data` em vez de defini-los inline (mesmo commit — §4). |
| `scripts/eval_retrieval.py` | CREATE | O harness: load frozen → prefix → IR evaluator → JSON + tabela markdown. Flags `--model`, `--dataset`, `--freeze`. |
| `data/eval/faq_bacen_corpus.jsonl` | CREATE (gerado via `--freeze`, commitado) | Corpus congelado: `{"doc_id", "text"}` (answers train+test). |
| `data/eval/faq_bacen_eval.jsonl` | CREATE (gerado via `--freeze`, commitado) | Queries+qrels congelados: `{"query_id", "query", "relevant_doc_ids"}` (split `test`). |
| `data/eval/banking_kb_eval.jsonl` | CREATE (hand-crafted, ~15 q) | Smoke set closed-loop; `{"query_id", "query", "relevant_doc_ids"}` referenciando paras do KB. |
| `models/eval/` | CREATE (dir) | Onde os `<run>.json` caem. Adicionar `.gitkeep` ou commitar o baseline. |
| `tests/unit/test_eval_retrieval.py` | CREATE | Testa pieces puras (loaders, metric-key extraction, markdown render, determinismo) com mock — sem baixar nada. |
| `.gitignore` | UPDATE (verificar) | Garantir que `data/eval/*.jsonl` e o baseline `models/eval/*.json` **não** sejam ignorados (precisam ser commitados). |

---

## Tasks

Executar em ordem. Cada task é atômica e verificável.

### Task 1: Esqueleto do harness + bootstrap + CLI
- **File**: `scripts/eval_retrieval.py`
- **Action**: CREATE
- **Implement**: shebang + docstring (usage). `import guardrails.env_bootstrap` como **primeira** import. `argparse` com `--model` (default `intfloat/multilingual-e5-small`), `--dataset` (`faq_bacen`|`banking_kb`, default `faq_bacen`), `--freeze` (flag; regenera os JSONL do FAQ_BACEN e sai), `--out-dir` (default `models/eval`). `main()` + `raise SystemExit(main())`.
- **Mirror**: `scripts/finetune_itau_embedding.py:182-209`
- **Validate**: `uv run python scripts/eval_retrieval.py --help`

### Task 2a: Extrair `load_faq_data` para módulo compartilhado
- **File**: `scripts/_faq_data.py` (CREATE) + `scripts/finetune_itau_embedding.py` (UPDATE)
- **Action**: CREATE + UPDATE (mesmo commit — §4)
- **Implement**: mover `load_faq_data` (e, se conveniente, `build_evaluator`) de `finetune_itau_embedding.py:37-110` para `scripts/_faq_data.py`. Em `finetune_itau_embedding.py`, substituir a definição por `from _faq_data import load_faq_data, build_evaluator` (com `import guardrails.env_bootstrap` mantido como primeira import). **Não** alterar comportamento do fine-tune — só relocar.
- **Mirror**: `scripts/finetune_itau_embedding.py:37-110`
- **Validate**: `uv run python scripts/finetune_itau_embedding.py --help` ainda funciona; `python -c "from scripts._faq_data import load_faq_data"`

### Task 2: Freeze do FAQ_BACEN (reuso de `load_faq_data`)
- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: `freeze_faq_bacen(out_dir="data/eval")` que importa `load_faq_data` de `scripts._faq_data` (módulo compartilhado da Task 2a — sem side-effects de `__main__`), pega `corpus/queries/relevant_docs`, e escreve **ordenado por doc_id/query_id** (determinismo):
  - `faq_bacen_corpus.jsonl` ← `{"doc_id", "text"}` para cada item do corpus
  - `faq_bacen_eval.jsonl` ← `{"query_id": "q_{i}", "query", "relevant_doc_ids": ["test_{i}"]}`
  Acionado só por `--freeze`. Imprime contagens (corpus N, queries M) e sai 0.
- **Mirror**: `scripts/finetune_itau_embedding.py:37-82` (não reimplementar a lógica de split — chamar a função)
- **Validate**: `uv run python scripts/eval_retrieval.py --freeze && wc -l data/eval/faq_bacen_*.jsonl` → corpus = train+test, eval = test count. Rodar 2× → `git diff` vazio (determinismo).

### Task 3: Loader dos splits congelados (lê do disco, não da rede)
- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: `load_frozen(dataset) -> (corpus, queries, relevant_docs)`. Para `faq_bacen`: lê os 2 JSONL. Para `banking_kb`: corpus derivado de `data/banking_kb/*.md` via `_split_paragraphs` (importar de `scripts.ingest_banking_kb`, com os mesmos UUID5 ids), queries de `banking_kb_eval.jsonl`. Retorna dicts no formato do evaluator. **Sem** `load_dataset()` aqui — só I/O local.
- **Mirror**: `scripts/ingest_banking_kb.py:_split_paragraphs` (reuso), formato de `tests/unit/test_embedding.py` para imports
- **Validate**: `python -c "from scripts.eval_retrieval import load_frozen; c,q,r=load_frozen('faq_bacen'); print(len(c),len(q),len(r))"`

### Task 4: Aplicar prefixos E5 + montar e rodar o evaluator
- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**: `run_eval(model_name, corpus, queries, relevant_docs, name)`:
  - bakear prefixos: `corpus = {k: f"passage: {v}" ...}`, `queries = {k: f"query: {v}" ...}` (D3)
  - `SentenceTransformer(model_name, device="cpu")`
  - `InformationRetrievalEvaluator(... accuracy_at_k=[1,3,5,10], precision_recall_at_k=[1,3,5,10], mrr_at_k=[10], ndcg_at_k=[10], map_at_k=[10])`
  - retornar o dict `results`
- **Mirror**: `scripts/finetune_itau_embedding.py:85-110` (build_evaluator) **mas com prefixos** (a diferença de D4)
- **Validate**: smoke com `--dataset banking_kb` (corpus pequeno, roda em segundos no CPU); confere que recall@10 ≥ recall@1.

### Task 5: Extração de métricas + emissão (JSON + markdown)
- **File**: `scripts/eval_retrieval.py`
- **Action**: UPDATE
- **Implement**:
  - `extract_metrics(results, name)` → dict limpo: `recall@{1,3,5,10}`, `mrr@10`, `ndcg@10`, `map@10` (lendo as chaves `{name}_cosine_*`)
  - `write_run_json(out_dir, payload)` com metadata: `model`, `dataset`, `prefixes_applied: true` (D4), `closed_loop` (True p/ banking_kb), `n_queries`, `n_corpus`, `timestamp` (UTC ISO), `seed`, e os números. Nome do arquivo: `{dataset}__{model_slug}__{ts}.json`.
  - `render_markdown(metrics)` → tabela pro stdout.
- **Mirror**: `scripts/finetune_itau_embedding.py:171-179` (loop de impressão de métricas)
- **Validate**: rodar `--dataset banking_kb` → tabela no stdout + JSON em `models/eval/`; `jq . models/eval/banking_kb__*.json` válido.

### Task 6: Smoke set `banking_kb_eval.jsonl` hand-crafted (~15 q, closed-loop)
- **File**: `data/eval/banking_kb_eval.jsonl`
- **Action**: CREATE
- **Implement**: ~15 perguntas em PT-BR sobre os docs de `data/banking_kb/`, cada uma com `relevant_doc_ids` apontando para o(s) UUID5 do(s) parágrafo(s) correto(s) (gerados pela mesma fórmula `uuid5(NAMESPACE, f"{path.name}:{idx}")` de `ingest_banking_kb.py`). **Declarar closed-loop** num comentário/campo. ⚠️ §1: este set é tautológico por construção — só prova plumbing, não qualidade de retrieval.
- **Mirror**: `scripts/ingest_banking_kb.py:24` (NAMESPACE), `:_split_paragraphs` (indexação dos paras)
- **Validate**: `load_frozen('banking_kb')` resolve todos os `relevant_doc_ids` contra o corpus derivado (0 ids órfãos).

### Task 7: Gerar e congelar o baseline e5-small
- **File**: `models/eval/<run>.json`
- **Action**: CREATE (commitado)
- **Implement**: `uv run python scripts/eval_retrieval.py --freeze` (uma vez) → depois `uv run python scripts/eval_retrieval.py --model intfloat/multilingual-e5-small --dataset faq_bacen`. Commitar os 2 JSONL congelados + o JSON do baseline.
- **Mirror**: —
- **Validate**: ⚠️ **§3 building-rigorously — green-on-first-try é AVISO**: comparar recall@5/MRR@10 com SOTA publicado de retrieval multilíngue PT-BR (e5-small em MTEB/MIRACL pt). Se os números vierem absurdamente altos (ex: recall@1 > 0.95), suspeitar de leakage residual ou de corpus trivial (poucos distractors) — investigar antes de aceitar. Sanity: rodar 2× e confirmar JSON idêntico (determinismo D7).

### Task 8: Testes unitários do harness (mock, sem rede)
- **File**: `tests/unit/test_eval_retrieval.py`
- **Action**: CREATE
- **Implement**: testar as peças **puras** sem baixar modelo/dataset:
  - `extract_metrics` mapeia chaves `{name}_cosine_*` corretamente (input = dict fixture)
  - `render_markdown` produz tabela com todas as métricas
  - `load_frozen` lê JSONL fixture de `tests/unit/fixtures/` e resolve ids
  - determinismo: freeze escreve linhas ordenadas
  - marcar o teste que carrega e5 real como `@pytest.mark.slow`/`network`
- **Mirror**: `tests/unit/test_embedding.py:19-50` (mock pattern), `conftest.py` para markers
- **Validate**: `uv run pytest tests/unit/test_eval_retrieval.py -m "not slow and not network" -q`

### Task 9: Garantir que os artefatos são commitados
- **File**: `.gitignore`
- **Action**: UPDATE (se necessário)
- **Implement**: conferir que `data/eval/*.jsonl` e `models/eval/*.json` não caem em regra de ignore (ex: `models/` amplo). Adicionar `!data/eval/`, `!models/eval/*.json` ou `.gitkeep` conforme o caso.
- **Validate**: `git status --porcelain data/eval models/eval` lista os arquivos novos.

---

## Risks & Mitigations

| Risco | Mitigação |
|------|------------|
| **R1 — Leakage residual** (corpus trivial, poucos distractors → recall inflado) | `load_faq_data` mantém answers de `train` como distractors (D5); §3 sanity vs SOTA na Task 7; declarar leakage statement no JSON e em SCRUM-40 |
| **R2 — Comparar com o eval antigo do fine-tune (sem prefixo)** | D4: anotar `prefixes_applied: true` no JSON; **não** reusar `models/itau-embedding-eval/`; flag explícita na doc |
| **R3 — Importar `load_faq_data` de um script com `__main__`** | **RESOLVIDO (2026-06-11):** extrair `load_faq_data` para módulo compartilhado `scripts/_faq_data.py`; tanto `finetune_itau_embedding.py` quanto `eval_retrieval.py` importam de lá. Refator do fine-tune feito no MESMO commit (§4 doc/code drift). Ver Task 2a. |
| **R4 — Map@k: qual k?** PRD diz "MAP" sem k | Fixar `map_at_k=[10]` e reportar como `MAP@10` explicitamente na tabela/JSON (sem ambiguidade) |
| **R5 — banking_kb ids órfãos** (parágrafo reindexado quebra gold) | Validação da Task 6 falha cedo se algum `relevant_doc_id` não existe no corpus derivado; corpus e gold derivam da MESMA fórmula UUID5 |
| **R6 — Tempo de encode do corpus FAQ no CPU** | Corpus FAQ é pequeno (centenas de pares); aceitável. banking_kb é o smoke rápido pra iterar a plumbing antes de rodar o FAQ |
| **R7 — Determinismo de floats no JSON** | Arredondar para 4 casas na serialização; ordenar chaves; rodar 2× e diff (Task 7) |

---

## Validation (gate da story)

```bash
# 1. Harness roda e congela
uv run python scripts/eval_retrieval.py --freeze
wc -l data/eval/faq_bacen_corpus.jsonl data/eval/faq_bacen_eval.jsonl

# 2. Baseline e5-small (manchete)
uv run python scripts/eval_retrieval.py --model intfloat/multilingual-e5-small --dataset faq_bacen

# 3. Smoke closed-loop reportado à parte
uv run python scripts/eval_retrieval.py --dataset banking_kb

# 4. Determinismo
uv run python scripts/eval_retrieval.py --freeze && git diff --exit-code data/eval/

# 5. Testes + lint
uv run pytest tests/unit/test_eval_retrieval.py -m "not slow and not network" -q
uv run ruff check scripts/eval_retrieval.py tests/unit/test_eval_retrieval.py
```

---

## Acceptance Criteria (do story SCRUM-37)

- [ ] `scripts/eval_retrieval.py` emite recall@{1,3,5,10}, MRR@10, nDCG@10, MAP@10 via `InformationRetrievalEvaluator`
- [ ] Split `test` do `Itau-Unibanco/FAQ_BACEN` congelado em `data/eval/faq_bacen_eval.jsonl` (+ corpus companion), seeded e commitado, reusando `load_faq_data` — **leakage-free declarado**
- [ ] Smoke `data/eval/banking_kb_eval.jsonl` (~15 q) roda no mesmo harness, reportado à parte, **marcado closed-loop** no JSON
- [ ] Baseline e5-small/384 salvo em `models/eval/<run>.json` e commitado
- [ ] Flags `--model` / `--dataset` (+ `--freeze`) funcionam
- [ ] Prefixos E5 aplicados (≠ do evaluator do fine-tune); `prefixes_applied: true` no JSON
- [ ] §3: números sanity-checados contra SOTA antes de aceitar; determinismo confirmado (diff vazio em rerun)
- [ ] `ruff` limpo, testes unitários (mock) passando

---

## Out of scope (outras stories — NÃO fazer aqui)

- Bake-off de 4 modelos + tabela de latência → **SCRUM-38**
- Score threshold + cross-encoder reranker + wiring em produção (`nodes.py`/`vector_store.py`/`config.yaml`) → **SCRUM-39**
- `docs/RAG.md`, interview notes, ADR-006 update, `LIMITATIONS.md` → **SCRUM-40**
- Flags `--reranker` / `--threshold` / `--hybrid` → reservadas no argparse como talking point, implementadas nas stories acima
