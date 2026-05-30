# PRD — Sprint de Avaliação (Baseline dos Validators)

> **Versão:** 1.0 · **Criado:** 2026-05-30 · **Status:** planejado
> **Escopo:** um sprint. Foco único: baseline de avaliação dos 5 validators do guardrail bancário.
> **Documentos relacionados:** plano de execução em [`.claude/agents/plans/sprint-eval-baseline.plan.md`](../plans/sprint-eval-baseline.plan.md); PRD do produto em [`PRD.md`](./PRD.md); limitações em [`LIMITATIONS.md`](../../../LIMITATIONS.md); regra-mestre em [`building-rigorously.md`](file:///home/germano/.claude/rules/building-rigorously.md).

---

## 1. Executive Summary

O guardrail bancário hoje "passa nos testes", mas os testes medem a coisa errada. As fixtures atuais são em grande parte **loop-fechado** (o mesmo agente escreveu rubrica, fixtures, matcher e modelo), pequenas (≈22 amostras por categoria) e reportam apenas **block rate** — recall de ataque. Não existe medição de **falso-positivo** (bloquear cliente legítimo), que para um chatbot bancário é tão grave quanto deixar passar um ataque. Resultado: um dashboard verde que prova consistência interna, não correção contra a realidade.

Este sprint entrega um **baseline de avaliação crível e não-vazado** dos 5 validators (jailbreak, toxicidade, out-of-scope, PII, compliance). "Crível" significa: dado de teste vindo de **fonte que o pipeline nunca consumiu**; métrica **dois-lados** (recall de ataque **+** taxa de falso-positivo), quebrada por idioma (PT-BR vs EN); e régua de release explícita. Os 4 validators determinísticos/offline viram **gate de CI**; o compliance (LLM-judge, online, não-determinístico) vira **baseline manual commitado**.

**Meta de MVP:** existir um `EVAL_BASELINE.md` commitado com a tabela dos 5 validators (recall, FPR, por idioma, kappa do compliance), 4 validators offline plugados no CI como gate, e uma **matriz de vazamento** documentando qual dataset pode tocar qual componente. Em uma frase: *transformar "achamos que funciona" em "medimos, em dado que o modelo nunca viu, e aqui estão os números — inclusive os ruins".*

---

## 2. Mission

Dar ao guardrail uma **medição honesta de quão bem ele realmente protege** — sem inflar números via loop fechado, e sem esconder onde ele falha.

**Princípios:**

1. **Anti-loop-fechado é inegociável** (building-rigorously §1). Descope é sempre na máquina de comparação, nunca na disciplina de origem de dados.
2. **Métrica dois-lados ou nenhuma.** Recall sem FPR é meia-métrica e é a metade perigosa.
3. **Honestidade sobre limites > cobertura fingida** (§7). Declarar o que não foi medido vale mais que um 100% suspeito.
4. **Um check externamente validado > cinco docs aspiracionais** (§8). Nenhum artefato a mais antes da primeira medição real.
5. **Régua antes do resultado** (§5). Definir piso/teto antes de medir; nunca afrouxar a régua pra caber o número.

---

## 3. Target Users

Este é um sprint de engenharia interna; os "usuários" do entregável são:

| Persona | Conforto técnico | Necessidade / dor |
|---|---|---|
| **O autor (Germano)** | alto | Saber, com número defensável, se cada validator funciona; ter base pra decidir fine-tune/RAG depois |
| **Revisor cético / entrevistador** | alto | Furar a narrativa: "me mostra que esse número não é loop fechado". Quer ver dado externo, FPR e limitações declaradas |
| **Cliente final do banco (indireto)** | n/a | Não ser bloqueado ao perguntar "qual meu saldo?" — representado pela métrica de **FPR** |
| **SME de compliance (futuro)** | alto, domínio regulatório | Validar se a rubrica R1–R5 bate com BACEN/CVM — fora deste sprint, declarado como gap |

---

## 4. MVP Scope

### In Scope — Core (avaliação)
- [ ] Métrica dois-lados (recall + FPR) por validator, **quebrada por idioma** (PT-BR/EN)
- [ ] Régua de release: recall ≥80% (piso) **e** FPR ≤2–3% (teto)
- [ ] **Jailbreak:** conjunto externo (HarmBench/AdvBench/wildjailbreak) + split de teste do Necent + benigno bancário
- [ ] **Toxicidade:** ataque externo held-out + benigno bancário (FAQ_BACEN)
- [ ] **Out-of-scope:** in-scope vs out-of-scope + FPR no split congelado do FAQ_BACEN
- [ ] **PII:** positivos via Faker `pt_BR` + negativos difíceis; cobrir camada regex/checksum **e** Presidio NER
- [ ] **Compliance:** Pergunta A (fidelidade à rubrica), ~50 casos, anotação humano + 2º LLM, reporte de **kappa**
- [ ] **Matriz de vazamento** commitada (qual dataset toca qual componente)
- [ ] **`EVAL_BASELINE.md`** commitado com a tabela consolidada

### In Scope — Técnico
- [ ] 4 validators offline plugados no **CI como gate** (verde/vermelho a cada push)
- [ ] Script de baseline **manual** do compliance (online, sob demanda)
- [ ] Correção do bloqueador de **disco local** (apontar `HF_HOME`/`HF_DATASETS_CACHE`/`TMPDIR`/cache uv pro HD externo)
- [ ] Resolver **conflito de coleção Qdrant** (`itau_faq` vs `banking_kb`) — define contra o que out-of-scope/RAG são avaliados
- [ ] Corrigir **ADR 005** (diz "sem Presidio"; código usa Presidio) ou criar ADR 007

### Out of Scope (backlog — decisões de design já fechadas)
- [ ] **Fine-tune de embedding** (e5-small + prefixos, só out-of-scope+RAG, nunca jailbreak; split congelado; portão "bate a base ou não entra")
- [ ] **Bancada de comparação parametrizada** (trocar chunking/embedding/reranker → mesma tabela)
- [ ] **Observabilidade** (OTel → Prometheus+Loki → Grafana; Langfuse=Extra; FPR-em-prod via amostragem+spike+feedback+shadow)
- [ ] **AWS nível A** (ADR de migração + auditoria de adapters)
- [ ] Justificativa comparativa final ("finalzão": qual chunking/embedding/reranker, com tabela)
- [ ] Compliance **Pergunta B** (rubrica vs BACEN/CVM real — exige SME)
- [ ] Limpeza de doc-drift: PRD ainda cita DeBERTa; `redis` não usado; streamlit dep; renumeração KB

---

## 5. User Stories

1. **Como autor**, quero medir recall **e** FPR de cada validator em dado externo, para saber se o guardrail funciona de verdade e não só no meu próprio dataset.
   *Ex.: jailbreak bloqueia 88% do HarmBench (PT-BR 82%, EN 94%) e tem FPR de 1,5% nas perguntas reais do FAQ_BACEN.*

2. **Como revisor cético**, quero ver a matriz de vazamento, para confirmar que o número de jailbreak não foi medido no próprio Necent que alimenta o índice L1c.
   *Ex.: matriz mostra "Necent → índice L1c + split-treino; HarmBench → só eval; nunca o contrário".*

3. **Como cliente do banco (via FPR)**, quero que "como contesto minha fatura?" não seja bloqueado, para não ser tratado como atacante.
   *Ex.: conjunto benigno de 100 perguntas bancárias reais com FPR medido e abaixo do teto.*

4. **Como autor**, quero um gate de CI nos 4 validators offline, para que uma regressão de FPR (tipo a do DeBERTa antigo, ~1.0 em PT-BR benigno) apareça como vermelho automático, não como anedota.

5. **Como autor**, quero gerar o dataset de PII com Faker `pt_BR` em vez de escrever os exemplos à mão, para que o gabarito venha de fonte externa ao meu código de regex.
   *Ex.: 500 CPFs/CNPJs/telefones válidos do Faker + 200 negativos difíceis (nº pedido, CEP, data).*

6. **Como autor**, quero anotar 50 casos de compliance junto a um 2º LLM e reportar o kappa, para ter humano-no-loop sem fingir expertise regulatória.
   *Ex.: kappa Germano-vs-GPT = 0.71 na fidelidade à rubrica; divergências sinalizadas pra revisão.*

7. **Como entrevistador**, quero ler em `LIMITATIONS.md`/`EVAL_BASELINE.md` o que o sistema **não** mede (rubrica vs norma real, recall PT-BR exaustivo), para confiar nos números que ele **mede**.

8. **Como autor (técnico)**, quero que o eval rode sem estourar o disco local, para conseguir executá-lo de fato.
   *Ex.: `HF_DATASETS_CACHE` aponta pro HD externo; `pytest -m adversarial` roda sem `ENOSPC`.*

---

## 6. Core Architecture & Patterns

**Abordagem:** o eval é uma camada de teste sobre o pipeline existente, não muda o produto. Reutiliza o arnês `tests/adversarial/` (com `block_rate_tracker` em `conftest.py`), estendido para **dois-lados** e **por-idioma**.

```
tests/
├── adversarial/
│   ├── fixtures/                 # datasets versionados (jsonl) — com header de fonte + licença
│   │   ├── jailbreak_external.jsonl      # HarmBench/AdvBench held-out (ESTENDER)
│   │   ├── jailbreak_necent_test.jsonl   # split de teste do Necent (NOVO)
│   │   ├── benign_banking.jsonl          # FPR — perguntas FAQ_BACEN (NOVO)
│   │   ├── pii_faker.jsonl                # Faker pt_BR + negativos difíceis (NOVO)
│   │   └── compliance_annotated.jsonl    # 50 casos + label humano + 2º LLM (NOVO)
│   ├── conftest.py               # tracker estendido: recall + FPR + por-idioma
│   └── test_*_pipeline.py        # um por validator
├── eval/                          # (NOVO) lógica de métrica reutilizável
│   ├── metrics.py                # recall, FPR, F1, balanced acc, por-idioma
│   └── leakage_matrix.md         # qual dataset toca qual componente
scripts/
├── gen_pii_faker.py              # (NOVO) gera positivos+negativos PII
├── split_necent.py               # (NOVO) congela split treino/val/teste do Necent
├── eval_compliance_manual.py     # (NOVO) baseline online, gera relatório + kappa
└── build_eval_baseline.py        # (NOVO) consolida tudo em EVAL_BASELINE.md
```

**Padrões-chave:**
- **Separação offline/online:** marcadores pytest `adversarial and not network` (CI gate) vs `adversarial and network` (manual). Já existe; estender.
- **Datasets como dado, não código:** cada `.jsonl` carrega header com fonte, licença, data de acesso e flag `native|translated`. Reprodutibilidade > conveniência.
- **Métrica pura e testável:** `eval/metrics.py` sem I/O, testável isoladamente (não cair no meta-loop de eval bugado).
- **Gabarito externo sempre que possível:** Faker (PII), datasets públicos (jailbreak/toxic), anotador humano (compliance). Hand-crafted só onde declarado.

---

## 7. Features (detalhe por validator)

### F-1 · Jailbreak — eval de 3 conjuntos
- **Conjunto A (Necent split-teste):** mede generalização *dentro da distribuição*. Pré-requisito: `split_necent.py` congela treino/val/teste; índice L1c só vê treino.
- **Conjunto B (externo: HarmBench/AdvBench/wildjailbreak):** mede generalização *no mundo aberto*. ~50–100 amostras bastam; o que importa é serem disjuntas de Necent/Octavio/JailbreakBench.
- **Conjunto C (benigno bancário):** mede FPR.
- **Saída:** recall A, recall B, FPR C — por idioma, com `layer_caught` agregado (quanto cada camada contribuiu).

### F-2 · Toxicidade — dois-lados
- Ataque: porção held-out de HateBR/RealToxicityPrompts (detoxify é off-the-shelf, então não há leakage de treino, mas separar do que já virou fixture).
- Benigno: FAQ_BACEN + frases-armadilha de gíria ("morrer de rir", "matar a curiosidade") — o FP que o `LIMITATIONS.md` já suspeita.

### F-3 · Out-of-scope — separação + FPR
- In-scope: split congelado do FAQ_BACEN. Out-of-scope: tópicos não-bancários.
- FPR mede o risco de bloquear pergunta bancária criativa.

### F-4 · PII — Faker + negativos difíceis
- Positivos: `Faker(locale="pt_BR")` → CPF/CNPJ/telefone/email/nome válidos em templates.
- Negativos difíceis: nº de pedido 11 díg., data, valor, protocolo, CEP — onde a regex sangra.
- Cobrir **as duas camadas:** regex/checksum **e** Presidio NER (nome/endereço). Corrigir ADR 005 no mesmo passo.

### F-5 · Compliance — Pergunta A + kappa
- ~50 outputs anotados por **Germano + 2º LLM de outra família** quanto à **fidelidade à rubrica declarada** (não correção regulatória).
- Reporta concordância judge-vs-rubrica e **kappa Germano-vs-2ºLLM**. Divergências viram lista de revisão.
- Pergunta B (rubrica vs BACEN real) = gap declarado, exige SME.

---

## 8. Technology Stack

- **Runtime/orquestração:** Python 3.x, pytest (+ marcadores `adversarial`, `network`), `uv`.
- **Datasets:** HuggingFace `datasets` — Necent (gated, `HF_TOKEN`), HarmBench/AdvBench/wildjailbreak, HateBR, RealToxicityPrompts, `Itau-Unibanco/FAQ_BACEN`.
- **Geração PII:** `Faker` locale `pt_BR`.
- **PII NER:** Presidio + spaCy `pt_core_news_sm` (já no código).
- **Modelos sob avaliação (já existentes):** Prompt-Guard-2 (gated), detoxify multilingual, `paraphrase-multilingual-MiniLM-L12-v2`, `intfloat/multilingual-e5-small`, porttagger + spaCy `pt_core_news_lg`.
- **Compliance / 2º anotador:** Claude Haiku (judge atual) + **um LLM de outra família** (GPT/Gemini) como anotador independente.
- **Métrica:** numpy / scikit-learn (`f1_score`, `cohen_kappa_score`, `confusion_matrix`).
- **CI:** GitHub Actions (estender `.github/workflows/ci.yml`) — `actions/cache` p/ modelos, `HF_TOKEN` secret.

---

## 9. Security & Configuration

- **Sem PII em log/fixture real:** Faker gera dados sintéticos; nenhum CPF real entra no repo. Fixtures de PII são geradas, não coletadas.
- **Segredos:** `HF_TOKEN` (datasets/modelos gated) e chave do 2º LLM via secret do CI / env local — nunca commitados.
- **Cache (bloqueador):** `HF_HOME`, `HF_DATASETS_CACHE`, `TMPDIR`, cache `uv` apontados pro HD externo (disco local cheio). Documentar em `.env.example` (que ainda não existe — criar).
- **Reprodutibilidade:** seed fixo no Faker e nos splits; datasets congelados em `.jsonl` versionado.
- **Fora de escopo:** auth/rate-limit do produto (já em `LIMITATIONS.md`), deploy.

---

## 10. Interface do Entregável (não-API)

Não há endpoint novo. As "interfaces" são:

```bash
# Gate de CI (offline) — roda a cada push
pytest -m "adversarial and not network"     # falha se recall <80% ou FPR >teto

# Baseline manual do compliance (online, $$, sob demanda)
python scripts/eval_compliance_manual.py --annotations tests/adversarial/fixtures/compliance_annotated.jsonl

# Consolidação
python scripts/build_eval_baseline.py        # gera/atualiza EVAL_BASELINE.md
```

Formato do `EVAL_BASELINE.md` (esboço):

| Validator | Fonte ataque | Samples | Recall PT-BR | Recall EN | FPR | Gate |
|---|---|---|---|---|---|---|
| jailbreak | HarmBench+Necent-test | … | … | … | … | CI |
| toxic | HateBR/RTP held-out | … | … | … | … | CI |
| out-of-scope | tópicos não-banc. | … | … | … | … | CI |
| pii | Faker + neg. difíceis | … | … | … | … | CI |
| compliance | 50 anotados (kappa=…) | … | n/a | n/a | … | manual |

---

## 11. Success Criteria

**Definição de sucesso do sprint:** existe um número defensável de recall **e** FPR pra cada validator, medido em dado que o componente correspondente nunca viu, com a régua aplicada e as limitações declaradas.

- [ ] Os 5 validators têm recall + FPR no `EVAL_BASELINE.md`, por idioma onde aplicável
- [ ] Matriz de vazamento commitada e consistente com os datasets usados
- [ ] 4 offline no CI como gate (falham de verdade quando a régua é violada — testado quebrando de propósito)
- [ ] Compliance: kappa reportado; divergências listadas; Pergunta B declarada como gap
- [ ] Bloqueadores #0–#3 resolvidos (disco, cache CI, ADR 005, coleção Qdrant)

**Indicadores de qualidade (sinais de rigor, não de vaidade):**
- Pelo menos **um número ruim** aparece no baseline (FPR ou recall PT-BR abaixo do esperado). Se tudo vier ≥95% de primeira → suspeitar de loop fechado (§3) e investigar antes de aceitar.
- O conjunto externo (B) tem recall **menor** que o split interno (A) — esperado; se forem iguais, há vazamento.

---

## 12. Implementation Phases

### Fase 0 — Destravar (≈0,5 dia)
- **Goal:** poder rodar o eval.
- **Deliverables:** [ ] cache redirecionado pro HD externo; [ ] `.env.example`; [ ] conflito coleção Qdrant resolvido; [ ] `HF_TOKEN` no CI.
- **Validação:** `pytest -m adversarial` roda localmente sem `ENOSPC`.

### Fase 1 — Métrica + datasets offline (≈2–3 dias)
- **Goal:** baseline dos 4 offline.
- **Deliverables:** [ ] `eval/metrics.py` (testado); [ ] split Necent congelado; [ ] conjunto externo jailbreak; [ ] benigno bancário; [ ] Faker PII + negativos; [ ] correção ADR 005; [ ] tracker estendido (recall+FPR+idioma).
- **Validação:** tabela parcial gerada; gate de CI falha quando se quebra a régua de propósito.

### Fase 2 — Compliance manual (≈1–1,5 dia)
- **Goal:** baseline do judge com humano-no-loop.
- **Deliverables:** [ ] 50 casos anotados por Germano; [ ] 2º LLM anotando os mesmos; [ ] `eval_compliance_manual.py` (kappa + concordância); [ ] Pergunta B declarada em `LIMITATIONS.md`.
- **Validação:** relatório com kappa e lista de divergências.

### Fase 3 — Consolidação + CI (≈0,5–1 dia)
- **Goal:** entregável final.
- **Deliverables:** [ ] `EVAL_BASELINE.md`; [ ] matriz de vazamento; [ ] 4 offline no `ci.yml`; [ ] `LIMITATIONS.md` atualizado com o que NÃO foi medido.
- **Validação:** CI verde com o gate ativo; revisor cético consegue rastrear cada número até a fonte.

---

## 13. Future Considerations

- **Fine-tune e5-small** (out-of-scope+RAG) avaliado pela bancada deste sprint — só entra se bater a base.
- **Bancada parametrizada** (chunking/embedding/reranker) → habilita a justificativa comparativa final.
- **Observabilidade** (OTel/Prometheus/Loki/Grafana) com FPR-em-produção via amostragem + spike + feedback + shadow mode.
- **Calibração de compliance** contra labels de SME (Cohen's kappa, ~100 casos) — fecha a Pergunta B.
- **Recall PT-BR exaustivo** contra suite adversarial completa (hoje spot-check).
- **AWS nível A→B** (adapters Bedrock/OpenSearch reais com mock).

---

## 14. Risks & Mitigations

| Risco | Mitigação |
|---|---|
| **Tudo vem verde de primeira** (loop fechado disfarçado, §3) | Régua antes do número; exigir conjunto externo disjunto; investigar qualquer 100% antes de aceitar; comparar recall A vs B (devem divergir) |
| **Dado externo "vaza" sem querer** (ex.: amostra que também está no índice) | Matriz de vazamento explícita + dedup por hash entre fixtures e fontes de treino/índice |
| **Disco local estoura no meio dos downloads** | Fase 0 redireciona todos os caches pro HD externo antes de qualquer `load_dataset` |
| **Prompt-Guard gated quebra o CI** | Decisão em aberto: (a) `HF_TOKEN` secret + cache, ou (b) tirar a camada gated do gate e medi-la no baseline manual |
| **Anotação de compliance enviesada/sem expertise** | Separar Pergunta A (consistência, não exige expertise) de B (regulatória, declarada como gap); 2º LLM independente + kappa expõem viés |
| **Tradução PT-BR mascara recall real** | Marcar `native|translated`; reportar separado; tratar traduzido como suplemento, nunca sinal primário |

---

## 15. Appendix

**Documentos:**
- Plano de execução: `.claude/agents/plans/sprint-eval-baseline.plan.md`
- PRD do produto (v2.0): `.claude/agents/PRDs/PRD.md` *(nota: contém doc-drift — cita DeBERTa, hoje é Prompt-Guard-2)*
- Limitações: `LIMITATIONS.md`
- Regra-mestre: `building-rigorously.md` (§1 anti-loop, §3 verde-suspeito, §5 régua, §7 honestidade, §8 volume≠rigor)
- ADRs: `adr/004-layered-jailbreak.md`, `adr/005-regex-pii-no-presidio.md` *(a corrigir)*, `adr/006-local-embeddings.md`

**Datasets-chave:**
- `Necent/llm-jailbreak-prompt-injection-dataset` (gated) — só treino/índice, **nunca** eval
- HarmBench / AdvBench / `allenai/wildjailbreak` — eval externo jailbreak
- HateBR / RealToxicityPrompts — toxicidade
- `Itau-Unibanco/FAQ_BACEN` — benigno bancário + RAG (split congelado)
- Faker `pt_BR` — gabarito PII
