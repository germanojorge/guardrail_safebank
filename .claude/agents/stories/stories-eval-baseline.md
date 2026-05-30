# Stories — Sprint de Avaliação (Baseline dos Validators)

> **PRD:** `.claude/agents/PRDs/PRD-eval-baseline.md` · **Projeto:** SCRUM · **Épico:** SCRUM-18
> **Princípio-mestre:** anti-loop-fechado (building-rigorously §1).
> **Criado no Jira em 2026-05-30** sob SCRUM-18. Mapa: S-01→SCRUM-19, S-02→20, S-03→21, S-04→22, S-05→23, S-06→24, S-07→25, S-08→26, S-09→27, S-10→28, S-11→29, S-12→30, S-13→31, S-14→32, S-15→33, S-16→34, S-17→35.

---

## Fase 0 — Destravar (pré-requisitos; bloqueiam o primeiro `pytest`)

### S-01 Redirecionar caches de ML/datasets pro HD externo + `.env.example`
**Type**: Technical · **Jira Type**: Task · **Priority**: High · **Complexity**: Small · **Phase**: 0 · **Labels**: infra, config

**Description**: As autor, quero apontar `HF_HOME`/`HF_DATASETS_CACHE`/`TMPDIR`/cache `uv` pro HD externo (que tem espaço), para que os downloads do sprint não estourem o **disco local** (cheio).

**Acceptance Criteria**:
- [ ] Given disco local cheio, when rodo `load_dataset`/`pytest -m adversarial`, then nenhum `ENOSPC` ocorre (staging/cache vão pro HD externo)
- [ ] Given um clone novo, when leio `.env.example`, then todas as variáveis de cache estão documentadas com exemplo
- [ ] Given `ML_CACHE_ROOT` e os caches HF/uv, then todos resolvem para um caminho com espaço

**Technical Notes**: ver bloqueador #0 do plano; `docker-compose.yml` já usa `ML_CACHE_ROOT`. Criar `.env.example` (não existe). Não commitar caminhos absolutos do dono.
**Dependencies**: Blocks S-04..S-17

---

### S-02 Resolver precedência de coleção Qdrant (`itau_faq` vs `banking_kb`)
**Type**: Bug · **Jira Type**: Bug · **Priority**: High · **Complexity**: Small · **Phase**: 0 · **Labels**: rag, config

**Description**: As autor, quero uma única coleção Qdrant definida de forma determinística, para saber **contra o que** out-of-scope/RAG são avaliados.

**Acceptance Criteria**:
- [ ] Given compose (`itau_faq`) e config.yaml (`banking_kb`), when a API sobe, then a precedência env-vs-YAML é explícita e documentada
- [ ] Given o eval de out-of-scope/RAG, then ele aponta para a coleção canônica decidida
- [ ] Given um teste, then a precedência é coberta (não regride)

**Technical Notes**: open_question #2; `guardrails/config.py`, `guardrails/adapters/vector_store.py`.
**Dependencies**: Blocks S-07, S-09 (out-of-scope)

---

### S-03 CI obtém os modelos (HF_TOKEN secret + cache) — decidir fork (a/b)
**Type**: Technical · **Jira Type**: Task · **Priority**: High · **Complexity**: Medium · **Phase**: 0 · **Labels**: ci, infra

**Description**: As autor, quero que o CI consiga carregar os modelos offline, para que o gate dos 4 validators rode de verdade.

**Acceptance Criteria**:
- [ ] Given Prompt-Guard-2 gated, when o CI roda, then ou (a) baixa com `HF_TOKEN` secret + `actions/cache`, ou (b) a camada gated sai do gate e vai pro baseline manual — **decisão registrada num ADR/PR**
- [ ] Given um run de CI limpo, then os modelos não-gated carregam sem erro
- [ ] Given runs subsequentes, then o cache de modelos é reaproveitado (run não baixa tudo de novo)

**Technical Notes**: decisão em aberto do plano. `.github/workflows/ci.yml`. Fork (a) recomendada.
**Dependencies**: Blocks S-16 (CI gate)

---

## Fase 1 — Métrica + datasets offline

### S-04 `eval/metrics.py` + extensão do tracker (dois-lados, por-idioma, kappa)
**Type**: Technical · **Jira Type**: Task · **Priority**: High · **Complexity**: Medium · **Phase**: 1 · **Labels**: eval, tests

**Description**: As autor, quero funções de métrica puras e testadas (recall, FPR, F1, balanced accuracy, por-idioma, Cohen's kappa), para medir os dois lados sem I/O acoplado.

**Acceptance Criteria**:
- [ ] Given listas de predição/label, when chamo as métricas, then recall/FPR/F1/balanced-acc retornam valores corretos (testados contra casos conhecidos à mão)
- [ ] Given um campo `lang` por amostra, when agrego, then as métricas saem quebradas por idioma (PT-BR/EN)
- [ ] Given `conftest.py`, when a suite adversarial roda, then o tracker reporta recall **e** FPR (não só block rate)
- [ ] Given `eval/metrics.py`, then ele não faz I/O e tem cobertura de teste unitário

**Technical Notes**: estender `tests/adversarial/conftest.py` (`block_rate_tracker`). scikit-learn pra `cohen_kappa_score`/`f1_score`.
**Dependencies**: Blocked by S-01 · Blocks S-05..S-11, S-15, S-16

---

### S-05 Congelar split do Necent (treino/val/teste) — `split_necent.py`
**Type**: Feature · **Jira Type**: Story · **Priority**: High · **Complexity**: Medium · **Phase**: 1 · **Labels**: eval, jailbreak, datasets

**Description**: As autor, quero um split congelado do Necent onde índice L1c e treino só veem o split de treino, para medir generalização interna sem testar em treino.

**Acceptance Criteria**:
- [ ] Given Necent, when rodo `split_necent.py` com seed fixo, then gera splits treino/val/teste reprodutíveis e versionados
- [ ] Given o índice L1c, then ele é (re)construído **apenas** com o split de treino
- [ ] Given o split de teste, then nenhum componente do pipeline o consome (entra só no eval)

**Technical Notes**: Necent é gated (HF_TOKEN). Ajustar `scripts/build_jailbreak_index.py` pra usar só treino.
**Dependencies**: Blocked by S-01, S-04 · Blocks S-13, S-15

---

### S-06 Conjunto externo de jailbreak (HarmBench/AdvBench/wildjailbreak) held-out
**Type**: Feature · **Jira Type**: Story · **Priority**: High · **Complexity**: Medium · **Phase**: 1 · **Labels**: eval, jailbreak, datasets

**Description**: As revisor cético, quero um conjunto de ataque de fonte **disjunta** de Necent/Octavio/JailbreakBench, para confirmar que o recall não foi medido no próprio dado de treino.

**Acceptance Criteria**:
- [ ] Given o `.jsonl`, then cada linha tem header de fonte/licença/data e flags `lang` + `native|translated`
- [ ] Given as fontes, then nenhuma amostra colide (hash) com Necent/Octavio/JailbreakBench
- [ ] Given o eval, then recall é reportado separando PT-BR-native, PT-BR-translated e EN
- [ ] Given o conjunto, then tem ≥50 amostras (volume não é o foco; disjunção é)

**Technical Notes**: HarmBench / AdvBench / `allenai/wildjailbreak`. Traduzido = suplemento rotulado.
**Dependencies**: Blocked by S-04 · Blocks S-13, S-15

---

### S-07 Conjunto benigno bancário (FAQ_BACEN) para FPR
**Type**: Feature · **Jira Type**: Story · **Priority**: High · **Complexity**: Small · **Phase**: 1 · **Labels**: eval, datasets, fpr

**Description**: As cliente do banco (via FPR), quero que perguntas bancárias reais não sejam bloqueadas, medido por um conjunto benigno compartilhado entre jailbreak/toxic/out-of-scope.

**Acceptance Criteria**:
- [ ] Given perguntas do `Itau-Unibanco/FAQ_BACEN`, then um `benign_banking.jsonl` é montado (split que não vaza pra fine-tune/seeds futuros)
- [ ] Given esse conjunto, when rodo jailbreak/toxic/out-of-scope, then o FPR é calculado contra ele
- [ ] Given o teto de FPR (≤2–3%), then o resultado é comparado à régua

**Technical Notes**: para jailbreak/toxic é fonte limpa; para out-of-scope/RAG, marcar como split congelado (não usar em fine-tune depois).
**Dependencies**: Blocked by S-04 · Blocks S-08, S-09, S-15, S-16

---

### S-08 Eval de toxicidade dois-lados (held-out + armadilhas de gíria)
**Type**: Feature · **Jira Type**: Story · **Priority**: Medium · **Complexity**: Medium · **Phase**: 1 · **Labels**: eval, toxic

**Description**: As autor, quero recall + FPR da toxicidade, incluindo gírias bancárias ("morrer de rir", "matar a curiosidade"), para medir o FP que o `LIMITATIONS.md` já suspeita.

**Acceptance Criteria**:
- [ ] Given HateBR/RealToxicityPrompts held-out (separado do que já é fixture), when avalio, then recall sai por idioma
- [ ] Given frases-armadilha de gíria PT-BR benigna, when avalio, then o FPR é medido e reportado
- [ ] Given a régua, then recall ≥80% e FPR ≤teto são verificados

**Technical Notes**: detoxify é off-the-shelf (sem leakage de treino), mas separar do conjunto já usado em fixtures.
**Dependencies**: Blocked by S-04, S-07 · Blocks S-15, S-16

---

### S-09 Eval de out-of-scope dois-lados (split congelado FAQ)
**Type**: Feature · **Jira Type**: Story · **Priority**: Medium · **Complexity**: Medium · **Phase**: 1 · **Labels**: eval, out-of-scope

**Description**: As autor, quero recall (out-of-scope) + FPR (in-scope) do validator de escopo, para saber se ele bloqueia pergunta bancária criativa.

**Acceptance Criteria**:
- [ ] Given in-scope (split congelado FAQ) e out-of-scope (tópicos não-bancários), when avalio, then separa corretamente e reporta FPR
- [ ] Given o split congelado, then nenhuma das perguntas será usada em fine-tune/seeds futuros
- [ ] Given a régua de FPR, then o resultado é comparado

**Technical Notes**: depende da coleção Qdrant canônica (S-02). Seeds atuais em `scripts/build_outofscope_seeds.py`.
**Dependencies**: Blocked by S-02, S-04, S-07 · Blocks S-15, S-16

---

### S-10 Gerador de PII com Faker + negativos difíceis
**Type**: Feature · **Jira Type**: Story · **Priority**: High · **Complexity**: Medium · **Phase**: 1 · **Labels**: eval, pii, datasets

**Description**: As autor, quero positivos de PII gerados pelo Faker `pt_BR` e negativos difíceis, para que o gabarito venha de fonte externa ao meu código de regex (quebra o loop fechado).

**Acceptance Criteria**:
- [ ] Given `gen_pii_faker.py` com seed, then gera positivos (CPF/CNPJ/telefone/email/nome válidos) em templates + `pii_faker.jsonl`
- [ ] Given negativos difíceis (nº pedido 11 díg., data, valor, protocolo, CEP), then estão no conjunto e medem FPR
- [ ] Given o eval de PII, then cobre **regex/checksum E Presidio NER** (nome/endereço), não só regex
- [ ] Given a régua, then recall e FPR são reportados

**Technical Notes**: `Faker(locale="pt_BR")`. Presidio + spaCy `pt_core_news_sm` já no código. Ver S-11 (ADR).
**Dependencies**: Blocked by S-04 · Blocks S-15, S-16

---

### S-11 Corrigir ADR 005 (regex "sem Presidio" contradiz o código)
**Type**: Bug · **Jira Type**: Bug · **Priority**: Medium · **Complexity**: Small · **Phase**: 1 · **Labels**: docs, adr, pii

**Description**: As revisor, quero o ADR de PII coerente com o código (que usa Presidio NER), para a doc não mentir (building-rigorously §4).

**Acceptance Criteria**:
- [ ] Given `adr/005`, when leio, then ele reflete regex+checksum **+ Presidio NER** (ou existe ADR 007 substituto)
- [ ] Given o `EVAL_BASELINE.md`, then a camada Presidio é mencionada no escopo de PII
- [ ] Given a correção, then é commitada no mesmo PR do eval de PII

**Technical Notes**: open_question #1; commit `e38468b`.
**Dependencies**: Blocked by S-10 (medir antes de redocumentar)

---

### S-12 Matriz de vazamento (`eval/leakage_matrix.md`)
**Type**: Technical · **Jira Type**: Task · **Priority**: High · **Complexity**: Small · **Phase**: 1 · **Labels**: eval, docs

**Description**: As revisor cético, quero uma matriz dizendo qual dataset pode tocar qual componente, para confirmar que nada de teste vazou pra treino/índice.

**Acceptance Criteria**:
- [ ] Given todos os datasets, then a matriz lista para cada um: treino/índice/seeds permitidos vs eval-only
- [ ] Given Necent, then aparece como "índice+treino; NUNCA eval externo"; HarmBench como "eval-only"
- [ ] Given a matriz, then é consistente com os `.jsonl` realmente usados (dedup por hash verificado)

**Technical Notes**: documento + (opcional) check automatizado de colisão por hash.
**Dependencies**: Blocked by S-05, S-06

---

## Fase 2 — Compliance (baseline manual)

### S-13 Montar e anotar 50 casos de compliance (Germano + 2º LLM) — Pergunta A
**Type**: Technical · **Jira Type**: Task · **Priority**: Medium · **Complexity**: Medium · **Phase**: 2 · **Labels**: eval, compliance, annotation

**Description**: As autor, quero 50 outputs anotados quanto à **fidelidade à rubrica declarada** por mim e por um 2º LLM de outra família, para ter humano-no-loop sem fingir expertise regulatória.

**Acceptance Criteria**:
- [ ] Given 50 outputs (variando R1–R5 + benignos), then cada um tem label humano (Germano) sobre violação-da-rubrica
- [ ] Given os mesmos 50, then um 2º LLM (GPT/Gemini) anota independentemente
- [ ] Given a anotação, then **nenhuma** mede "rubrica vs BACEN real" (Pergunta B) — só fidelidade à rubrica
- [ ] Given `compliance_annotated.jsonl`, then carrega ambos os labels + flag `closed_loop`

**Technical Notes**: Pergunta A vs B do PRD §F-5. 2º LLM = família diferente do judge (Claude).
**Dependencies**: Blocked by S-04 · Blocks S-14

---

### S-14 `eval_compliance_manual.py` — kappa + concordância + relatório
**Type**: Technical · **Jira Type**: Task · **Priority**: Medium · **Complexity**: Medium · **Phase**: 2 · **Labels**: eval, compliance, network

**Description**: As autor, quero um script manual que rode o judge sobre os 50 casos e reporte kappa (Germano vs 2º LLM) e concordância judge-vs-rubrica, para ter o baseline congelado do compliance.

**Acceptance Criteria**:
- [ ] Given os 50 anotados, when rodo o script (marcador `network`), then sai concordância judge-vs-label + kappa Germano-vs-2ºLLM
- [ ] Given divergências, then são listadas para revisão
- [ ] Given o resultado, then **não** entra no gate de CI (é manual, declarado como medição única)
- [ ] Given `LIMITATIONS.md`, then a Pergunta B fica declarada como gap de SME

**Technical Notes**: usa API Claude (judge) + API 2º LLM → custo + não-determinístico. Marcar `pytest.mark.network` ou script standalone.
**Dependencies**: Blocked by S-13 · Blocks S-15

---

## Fase 3 — Consolidação + CI

### S-15 `build_eval_baseline.py` + `EVAL_BASELINE.md`
**Type**: Feature · **Jira Type**: Story · **Priority**: High · **Complexity**: Medium · **Phase**: 3 · **Labels**: eval, docs

**Description**: As autor/entrevistador, quero um `EVAL_BASELINE.md` consolidado com a tabela dos 5 validators, para ter um número rastreável até a fonte de cada um.

**Acceptance Criteria**:
- [ ] Given todos os evals, when rodo o consolidador, then `EVAL_BASELINE.md` traz recall+FPR por idioma dos 4 offline + kappa do compliance
- [ ] Given o doc, then cada número aponta para a fonte/fixture (rastreável)
- [ ] Given um sinal de qualidade, then ≥1 número "ruim" aparece (FPR ou recall PT-BR) — se tudo ≥95%, investigar loop fechado antes de aceitar (§3)
- [ ] Given recall A (Necent-test) vs B (externo), then B ≤ A (se iguais, suspeitar de vazamento)

**Technical Notes**: §11 do PRD tem o esboço da tabela.
**Dependencies**: Blocked by S-05..S-10, S-14

---

### S-16 Plugar os 4 validators offline no CI como gate
**Type**: Technical · **Jira Type**: Task · **Priority**: High · **Complexity**: Medium · **Phase**: 3 · **Labels**: ci, eval, tests

**Description**: As autor, quero `pytest -m "adversarial and not network"` como gate de CI, para que uma regressão de FPR/recall vire vermelho automático, não anedota.

**Acceptance Criteria**:
- [ ] Given o gate, when recall <80% ou FPR >teto, then o CI falha
- [ ] Given uma quebra proposital (baixar régua de mentira / injetar FP), then o gate **realmente** falha (testado)
- [ ] Given compliance (network), then **não** está no gate
- [ ] Given o run, then usa os modelos cacheados (S-03)

**Technical Notes**: `.github/workflows/ci.yml`; marcadores já existem (`adversarial`, `network`).
**Dependencies**: Blocked by S-03, S-07, S-08, S-09, S-10

---

### S-17 Atualizar `LIMITATIONS.md` com o que NÃO foi medido
**Type**: Technical · **Jira Type**: Task · **Priority**: Medium · **Complexity**: Small · **Phase**: 3 · **Labels**: docs

**Description**: As entrevistador, quero ler explicitamente o que o baseline **não** cobre, para confiar no que ele cobre (building-rigorously §7).

**Acceptance Criteria**:
- [ ] Given `LIMITATIONS.md`, then declara: rubrica-vs-norma (Pergunta B), recall PT-BR exaustivo, traduzido≠native, conta bancária/CNPJ unformatted
- [ ] Given o doc, then aponta para `EVAL_BASELINE.md` e a matriz de vazamento
- [ ] Given doc-drift, then a nota de "PRD cita DeBERTa" fica registrada como pendência

**Dependencies**: Blocked by S-15

---

## Resumo

- **17 stories** · Fase 0: 3 · Fase 1: 9 · Fase 2: 2 · Fase 3: 3
- **Tipos:** Story (7), Task (8), Bug (2)
- **Caminho crítico:** S-01 → S-04 → (datasets) → S-15 → S-16/S-17
