# Sprint Plan — Baseline de Avaliação dos Validators

> **Criado:** 2026-05-30 · **Status:** planejado (não iniciado)
> **Origem:** sessão `/grill-me` (13 grills) — planejamento da próxima sprint.
> **Foco único:** medir um baseline **crível e não-vazado** dos 5 validators. Tudo que não for medição entra no backlog.

---

## Objetivo

Sair de "block rate em fixtures majoritariamente loop-fechado" para um **baseline de avaliação dois-lados** (recall de ataque + taxa de falso-positivo), por idioma, medido em **dado externo que o pipeline nunca viu**. Entregável concreto: `EVAL_BASELINE.md` commitado + 4 validators offline plugados no CI como gate.

O princípio que governa tudo (building-rigorously §1, §3, §5): **descope é na máquina de comparação, nunca na disciplina anti-vazamento.** Um baseline medido em dado loop-fechado é pior que não ter baseline.

---

## Decisões travadas (o que ESTE sprint faz)

| # | Decisão |
|---|---|
| 1 | Foco único: **baseline de avaliação dos 5 validators**. Observabilidade, fine-tune, bench de comparação, outros RAG → **backlog** |
| 2 | **Métrica dois-lados:** recall (ataque) + **FPR** (benigno), reportados juntos, **quebrados por idioma** (PT-BR vs EN). Headline = F1/balanced accuracy com recall e FPR embaixo |
| 3 | **Régua de release:** recall ≥80% (piso) **E** FPR ≤2–3% em queries bancárias reais (teto). As duas como gate; nenhuma sozinha vale |
| 4 | **Anti-vazamento inegociável:** conjunto de teste de fonte que nenhum componente (índice, fine-tune, fixtures, seeds) consumiu. Manter **matriz de vazamento** no repo |
| 5 | **Jailbreak:** (a) split de teste do Necent (mede generalização interna) + (b) conjunto externo de **outra fonte** — HarmBench/AdvBench/wildjailbreak, **não** Necent/Octavio/JailbreakBench (mede generalização real) + (c) benigno bancário (mede FPR). Marcar cada linha com `lang` e `native\|translated`. Traduzido = suplemento rotulado, nunca o sinal PT-BR primário |
| 6 | **Toxic + out-of-scope:** mesmo arnês dois-lados. Benigno = **perguntas do `Itau-Unibanco/FAQ_BACEN`** (split congelado), que para esses validators é fonte limpa de FPR |
| 7 | **PII:** positivos gerados com **Faker `pt_BR`** (gabarito externo, não-autor) injetados em templates + **negativos difíceis** (nº de pedido 11 díg., data, valor, protocolo, CEP) pra medir FPR. Reais (HAREM/LeNER-Br) só como suplemento de nome/endereço |
| 8 | **Compliance:** separar duas perguntas. **Pergunta A** ("o judge aplica a rubrica declarada com consistência?") = anotada por **você + 2º LLM de outra família**, ~50 casos, reportar **kappa**. Não exige expertise regulatória. **Pergunta B** ("a rubrica R1–R5 bate com BACEN/CVM real?") = exige SME → **declarada como gap**, não medida |
| 9 | **Mecânica CI:** 4 validators **offline** (jailbreak, toxic, out-of-scope, PII) viram **gate de CI** (verde/vermelho a cada push, com a régua #3). **Compliance** = online ($, não-determinístico, depende das 50 anotações) → **script manual**, baseline congelado e commitado, declarado como "medição manual, não contínua" |
| 10 | **Entregável:** `EVAL_BASELINE.md` com tabela dos 5 (recall, FPR, por idioma, kappa do compliance) + 4 offline no CI + matriz de vazamento |

### Embasamento técnico das escolhas (pra os docs/entrevista)

- **Métrica dois-lados:** block rate sozinho é metade da métrica — um validator que bloqueia tudo tem 100% de block rate e é inútil. Pra chatbot bancário, FPR (bloquear cliente real) é tão grave quanto FN.
- **Anti-vazamento jailbreak:** a camada L1c **guarda os textos do Necent dentro do índice** → testar em Necent = testar em treino. Split do Necent mede generalização *dentro da distribuição*; fonte externa mede generalização *no mundo aberto*.
- **Faker pra PII:** o gabarito vem do Faker, não do autor da regex → quebra o loop fechado e gera volume.
- **Compliance A vs B:** viés independente do anotador é normal e mensurável (kappa); viés *idêntico* (mesmo agente escreve rubrica+fixture+judge) é o que é fatal. Separar A de B permite ter humano-no-loop sem fingir expertise regulatória.

---

## 🔴 Bloqueadores (resolver ANTES ou no começo do sprint)

| # | Bloqueador | Impacto | Ação |
|---|---|---|---|
| 0 | **Disco LOCAL cheio** (o HD externo, onde mora `ML_CACHE_ROOT`, tem espaço — o problema é o disco local) | Mesmo com o cache de modelos no HD externo, **downloads de dataset, staging temporário do HF, caches uv/pip e imagens Docker caem por padrão no disco local**. O sprint baixa vários datasets novos (HarmBench/AdvBench/FAQ_BACEN) → risco de estourar o local no meio | Apontar `HF_HOME`/`HF_DATASETS_CACHE`/`TMPDIR`/cache uv pro HD externo também (não só o de modelos); limpar disco local. Pré-requisito do sprint |
| 1 | **`ML_CACHE_ROOT` hardcoded ao HD do dono** | CI não tem esse disco; precisa baixar modelos. **Prompt-Guard-2 é gated** (exige `HF_TOKEN`) | Ver "Decisão em aberto" abaixo |
| 2 | **ADR 005 contradiz o código** (diz "regex puro, sem Presidio"; código usa Presidio NER) | Eval de PII tem que cobrir **a camada Presidio (nome/endereço)**, não só regex; ADR precisa correção (§4) | Corrigir ADR 005 ou criar ADR 007 no mesmo sprint do eval de PII |
| 3 | **Conflito de coleção Qdrant** (compose `itau_faq` vs config.yaml `banking_kb`) | Define **contra o que** out-of-scope/RAG são avaliados → reprodutibilidade do baseline | Resolver precedência env vs YAML antes de medir |

### Decisão em aberto — como o CI obtém os modelos (a confirmar)

- **(a) — RECOMENDADA (a confirmar):** CI baixa do HF a cada run + `actions/cache`, com `HF_TOKEN` secret pro Prompt-Guard gated. Honesto, run mais lento.
- (b) Tirar Prompt-Guard (gated) do gate de CI; rodar no CI só layers não-gated (regex/POS/semantic/detoxify/MiniLM) e medir a camada Prompt-Guard junto do baseline manual.
- (c) outra.

---

## 🟢 Backlog (decisões já tomadas, implementação adiada)

Estas saíram do sprint mas as **decisões de design já estão fechadas** — quando virarem sprint, é só executar.

### Observabilidade (sprint próprio)
- Stack: **OTel (instrumentação) → Prometheus (métricas) + Loki (logs) → Grafana (dashboard)**. Tudo OSS/grátis, via docker-compose.
- **Langfuse = Extra** (redundante dado o Grafana; cobre custo/verdict do judge via Prometheus+Loki).
- A pergunta difícil — **FPR em produção** (sem rótulo): resolver com **amostragem de bloqueios p/ revisão humana + alerta em spike de block rate + loop de feedback do usuário + shadow mode** pra promover modelo novo.

### Fine-tune de embedding (sprint próprio)
- É pra **out-of-scope + RAG**, **NÃO** jailbreak (fine-tunar em FAQ bancário deformaria o espaço e pioraria a separação de paráfrases de ataque).
- **Padronizar em `e5-small` com prefixos `query:`/`passage:`** pros dois consumidores (hoje RAG usa e5, out-of-scope usa MiniLM, e o script fine-tuna MiniLM — incoerente).
- **Split congelado do FAQ_BACEN** que o fine-tune nunca vê, usado pro nDCG do RAG **e** pro FPR benigno do out-of-scope (mesma armadilha de vazamento).
- **Portão:** o fine-tunado só entra em produção se **bater a base crua** no split congelado (nDCG@5 maior **e** FPR igual-ou-menor). Senão vira talking point, não código.

### Bancada de comparação + justificativa final ("finalzão")
- Eval **parametrizado por config** (trocar chunking/embedding/reranker → mesma tabela) pra que o doc final de justificativa (qual chunking — semântico vs fixo vs parágrafo —, qual embedding, qual reranker, com tabela comparativa) seja "rodar e colar", não reconstruir.
- Hoje o chunking é **split por parágrafo ingênuo** (não avaliado); top_k=3, sem reranker — **defaults, não escolhas**. A justificativa honesta vem do número, não da prosa.

### AWS (decidir/documentar, sprint próprio)
- **Nível A:** narrativa + ADR do mapa de migração (Bedrock, ECS/Fargate ou Lambda, OpenSearch, Secrets Manager) **+ auditoria dos adapters** provando que Qdrant/ST/Anthropic não vazam pela interface.
- Sinal positivo: o adapter `VectorStore` **está limpo** (interface genérica, imports Qdrant lazy/contidos, `InMemoryVectorStore` fake). Falta auditar `embedding` e `llm`.
- Nível B (escrever `BedrockProvider`/`OpenSearchVectorStore` reais com mock) e Nível C (deploy real, $$$) = Extras.

### Limpeza / doc-drift (§4)
- **PRD inteiro ainda cita `DeBERTa`** (`protectai/deberta-v3...`) como camada load-bearing — foi trocado por Prompt-Guard-2 + arquitetura de 4 camadas. Corrigir.
- `redis>=7.4.0` declarado e nunca usado; `streamlit` optional-dep vs `Dockerfile.ui`; renumeração da KB uncommitted.

---

## Tamanho honesto

5 validators × (montar dataset externo + medir) + 50 anotações manuais de compliance + 2 correções de bloqueador (cache/CI, ADR/Qdrant) = **sprint cheio**. Se apertar, a ordem de corte sugerida: compliance (vira só Pergunta A mínima) → PII (reduz negativos difíceis) — **nunca** cortar a disciplina anti-vazamento dos offline.
