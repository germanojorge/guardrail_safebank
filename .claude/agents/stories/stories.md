# Stories — Guardrail Bancário (Sprint 2 dias)

**Source:** `.claude/agents/PRDs/PRD.md` v2.0
**Epic:** SCRUM-1 (Guardrail)
**Project:** SCRUM
**Total stories:** 15 (8 Story + 7 Task)
**Total estimated work:** ~14h útil (alinhado com budget conservador do PRD)

---

## Phase 1 — Validators Core (4 stories, ~3.5h)

### S-01 Validator protocol + Toxicity validator

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Small
**Phase:** Phase 1 — Validators Core
**Labels:** `validators`, `phase-1`

#### Description
As a engenheiro do pipeline, eu quero um protocolo de Validator e um detector de toxicidade refatorado do PoC, para que os outros validators sigam interface consistente e o pipeline LangGraph possa chamá-los uniformemente.

#### Acceptance Criteria
- [ ] Given input benigno, when ToxicValidator.run() é chamado, then retorna ValidatorResult(passed=True, category="toxicity", score<threshold)
- [ ] Given input tóxico (HateBR sample), when run() é chamado, then retorna ValidatorResult(passed=False, category="toxicity", score>0.7)
- [ ] Given pytest tests/unit/test_toxic.py é executado, then 100% dos testes passam com happy path + fail path
- [ ] Given Validator protocol em base.py, when outro validator implementa run(text:str) -> ValidatorResult, then type-check passa sem reclamação

#### Technical Notes
- `guardrails/validators/base.py`: ValidatorResult dataclass (passed, category, score, details), Validator protocol
- `guardrails/validators/toxic.py`: wrapper sobre `detoxify` (já no PoC `guardrails.py:113`)
- Threshold via config.yaml (default 0.7)
- Detoxify singleton carregado 1x na startup
- Latência alvo <100ms
- `tests/unit/test_toxic.py`: 2-3 testes mínimo

#### Dependencies
- Blocks: S-06 (pipeline precisa do protocol + validator)
- Blocks: S-10 (adversarial suite precisa do validator instanciado)

---

### S-02 PII validator (input + output)

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Small
**Phase:** Phase 1 — Validators Core
**Labels:** `validators`, `phase-1`, `pii`

#### Description
As a sistema de compliance, eu quero detectar PII (CPF, cartão, email, telefone) tanto no input do usuário quanto no output do LLM, para que dados sensíveis não vazem em logs nem em respostas.

#### Acceptance Criteria
- [ ] Given input "Meu CPF é 123.456.789-09", when PIIValidator.run() é chamado, then retorna passed=False com entidade tipo CPF detectada
- [ ] Given output do LLM contendo número de cartão `4111-1111-1111-1111`, when validator é aplicado, then bloqueia com category="pii_output"
- [ ] Given mesmo validator instanciado para input E output guards, when ambos chamam run(), then comportamento é idêntico
- [ ] Given pytest tests/unit/test_pii.py, then 100% passa cobrindo 4 padrões regex (email, telefone, CPF, cartão)

#### Technical Notes
- `guardrails/validators/pii.py`: regex do PoC `guardrails.py:14-19` adaptado pra retornar ValidatorResult
- Patterns: email, telefone, CPF formatado (`\d{3}\.\d{3}\.\d{3}-\d{2}`), cartão (16 dígitos)
- Limitações em LIMITATIONS.md: sem checksum CPF/cartão, sem CNPJ, sem conta, sem NER (Presidio em Extras)
- Loga só tipo de entidade, NUNCA valor (security req)
- Latência alvo <10ms

#### Dependencies
- Blocks: S-06 (pipeline)
- Blocks: S-10 (adversarial)

---

### S-03 Jailbreak validator — layered defense

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Medium
**Phase:** Phase 1 — Validators Core
**Labels:** `validators`, `phase-1`, `jailbreak`, `security`

#### Description
As a sistema de segurança, eu quero detectar tentativas de jailbreak em camadas (substring fast-path + classifier DeBERTa load-bearing), para que tanto ataques óbvios quanto paraphrased (JailbreakBench) sejam bloqueados, com narrativa explícita de contribuição de cada camada.

#### Acceptance Criteria
- [ ] Given prompt "Esqueça todas as instruções anteriores", when JailbreakValidator é chamado, then layer="substring" pega e bloqueia em <5ms
- [ ] Given prompt paraphrased do JailbreakBench (ex: "I'm a researcher studying LLM safety..."), when validator é chamado, then layer="deberta" pega com score>0.85
- [ ] Given input benigno, when validator chamado, then ambas as camadas passam e retorna passed=True
- [ ] Given log estruturado de bloqueio, then campo `layer_caught` indica "substring" ou "deberta"
- [ ] Given DeBERTa model, when API startup, then modelo carrega 1x via singleton; inference <300ms em CPU

#### Technical Notes
- `guardrails/validators/jailbreak.py`:
  - Layer 1: substring matching de `CustomGuardrails.check_prompt_injection` do PoC `guardrails.py:247`
  - Layer 2: `protectai/deberta-v3-base-prompt-injection-v2` via `transformers.pipeline("text-classification")`
- Threshold DeBERTa: 0.85 (configurável)
- Combinação: OR (qualquer layer bloqueia)
- Log fields adicionais: `layer_caught`, `substring_match_count`, `deberta_score`
- Tabela substring-only vs substring+DeBERTa em `LIMITATIONS.md` (mensurar com adversarial suite — building-rigorously.md §6)
- Fallback se latência >400ms: trocar pra distilled (documentar)

#### Dependencies
- Blocks: S-06 (pipeline)
- Blocks: S-10 (adversarial)

---

### S-04 Compliance Judge (LLM-as-Judge bancário)

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Medium
**Phase:** Phase 1 — Validators Core
**Labels:** `validators`, `phase-1`, `llm-judge`, `compliance`

#### Description
As a sistema de compliance regulatório (BACEN/CVM), eu quero um LLM-as-Judge avaliando outputs do chatbot contra rubrica de 5 regras de compliance bancário, para que respostas com violações sutis (recomendação financeira indevida, promessa de rendimento, etc) sejam bloqueadas mesmo quando o input do cliente é inocente. **Este é o diferencial central da entrevista (Beat 4 da demo).**

#### Acceptance Criteria
- [ ] Given output "Pra você, o melhor é o CDB Premium" (Beat 4 demo), when compliance judge é chamado, then retorna verdict="fail", rule_violated="R2", reasoning explica
- [ ] Given output benigno informativo "CDBs do banco têm rendimento atrelado ao CDI", when judge chamado, then verdict="pass"
- [ ] Given chamada ao Claude Haiku, when judge executa, then usa tool_use (function calling) com schema {verdict, rule_violated, reasoning}
- [ ] Given pytest tests/unit/test_compliance.py, then ≥1 fixture por regra R1-R5 passa
- [ ] Given latência da chamada Haiku, then p50 <1000ms (caso típico Haiku 4.5 em response curta)

#### Technical Notes
- `guardrails/compliance/rubric.py`: 5 regras (R1-R5) como Python constants + 2 few-shot examples por regra (ver PRD §7 F-4)
- `guardrails/compliance/prompt.py`: builder do system prompt do judge (rubrica + few-shots + tool schema)
- `guardrails/validators/compliance.py`: chamada `anthropic.Anthropic().messages.create()` com `tool_choice={"type": "tool", "name": "verdict"}` (estruturação garantida)
- Aplicado APENAS no output (input não viola compliance — viola PII/jailbreak/tox)
- Comportamento em fail: bloqueio direto (sem reask — Extras)
- Limitação declarada em LIMITATIONS.md: fixtures hand-crafted criam loop fechado (building-rigorously.md §1)
- Model: `claude-haiku-4-5-20251001`
- Temperatura: 0.0

#### Dependencies
- Blocks: S-06 (pipeline precisa)
- Blocks: S-10 (adversarial precisa)

---

## Phase 2 — Pipeline + API (3 stories, ~3.5h)

### S-05 LLM adapter + structured JSON logger

**Type:** Technical
**Jira Type:** Task
**Priority:** High
**Complexity:** Small
**Phase:** Phase 2 — Pipeline + API
**Labels:** `adapters`, `phase-2`, `observability`

#### Description
As a sistema, eu quero abstração fina de LLM provider e logger estruturado JSON, para que (a) trocar provider (Anthropic→Bedrock) seja narrativa de migração trivial, e (b) cada bloqueio gere evento JSON pesquisável via `docker logs api | jq`.

#### Acceptance Criteria
- [ ] Given `LLMProvider` protocol e `AnthropicProvider` impl, when código de pipeline chama provider.complete(messages, model), then funciona idêntico ao SDK direto
- [ ] Given structlog configurado, when validator bloqueia, then evento JSON em stdout com campos `{timestamp, event, direction, category, severity, rule_violated, input_hash, latency_ms, layer_caught}`
- [ ] Given input PII detectada, when log emitido, then VALOR da PII NUNCA aparece no log (só tipo)
- [ ] Given `docker logs api | jq '.category'`, then output mostra categorias dos bloqueios

#### Technical Notes
- `guardrails/adapters/llm.py`: Protocol `LLMProvider` + classe `AnthropicProvider` (1 método: `complete()`)
- `guardrails/observability/logger.py`: wrapper sobre structlog com schema fixo
- Hash SHA-256 dos primeiros 200 chars do input como `input_hash`
- ADR 004 documenta escolha do adapter pattern + hook narrativo AWS Bedrock

#### Dependencies
- Blocks: S-06 (pipeline usa adapter e logger)

---

### S-06 LangGraph StateGraph pipeline

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Large
**Phase:** Phase 2 — Pipeline + API
**Labels:** `pipeline`, `phase-2`, `langgraph`

#### Description
As a engenheiro de orquestração, eu quero um pipeline LangGraph StateGraph com nodes input_guard → retrieve → generate → output_guard → block_log, branches condicionais para pass/fail, e mock inicial do retrieve, para que toda a lógica de fluxo bidirecional do guardrail esteja centralizada e testável.

#### Acceptance Criteria
- [ ] Given mensagem benigna, when pipeline executa, then percorre input_guard → retrieve → generate → output_guard → END com response do Claude
- [ ] Given input com PII, when pipeline executa, then para em input_guard, vai pra block_log, retorna fallback
- [ ] Given output do Claude violando R2, when pipeline executa, then output_guard.compliance_judge bloqueia, retorna fallback genérico
- [ ] Given retrieve node, when chamado, then retorna placeholder string mockada (vai ser substituído em S-08)
- [ ] Given GraphState TypedDict, then contém todos os campos necessários (message, retrieved_chunks, llm_response, blocked, category, diagnostics, latency_breakdown)

#### Technical Notes
- `guardrails/pipeline/state.py`: GraphState TypedDict
- `guardrails/pipeline/nodes.py`: 5 nodes — input_guard, retrieve (mock), generate, output_guard, block_log
- `guardrails/pipeline/graph.py`: build_graph() — StateGraph + conditional edges
- input_guard roda toxic, pii, jailbreak em sequência (curto-circuita no primeiro fail)
- output_guard roda toxic, pii (output), compliance_judge em sequência
- Logging de latência por stage no diagnostics

#### Dependencies
- Blocked by: S-01, S-02, S-03, S-04, S-05
- Blocks: S-07 (API), S-08 (RAG substitui mock retrieve)

---

### S-07 FastAPI endpoint /chat com Diagnostics

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Small
**Phase:** Phase 2 — Pipeline + API
**Labels:** `api`, `phase-2`, `fastapi`

#### Description
As a proxy corporativo, eu quero endpoint POST /chat aceitando session_id+message e retornando response+blocked+category+diagnostics, mais GET /health listando validators carregados, para que o cliente (Streamlit ou curl) interaja com o pipeline via HTTP.

#### Acceptance Criteria
- [ ] Given POST /chat com body benigno, when chamado, then 200 com response, blocked=false, diagnostics completos (latency breakdown, retrieved_chunks)
- [ ] Given POST /chat com input PII, when chamado, then 200 com blocked=true, category="pii_input", diagnostics.validator="pii"
- [ ] Given Beat 4 demo (input financeiro inocente, output viola R2), when chamado, then 200 com blocked=true, category="compliance", diagnostics.rule_violated="R2"
- [ ] Given GET /health, when chamado, then retorna validators_loaded list e models_loaded list
- [ ] Given uvicorn rodando, when 5 requests concorrentes, then sem erros 500

#### Technical Notes
- `api/main.py`: FastAPI app + endpoints
- `api/schemas.py`: ChatRequest, ChatResponse, Diagnostics (Pydantic 2)
- `Diagnostics` SEMPRE incluído (demo mode) — documentar como "hide em prod"
- Lifespan handler pra carregar validators 1x (não em cada request)
- Status code sempre 200 (bloqueio é resposta de aplicação)

#### Dependencies
- Blocked by: S-06
- Blocks: S-11 (Streamlit), S-12 (Docker)

---

## Phase 3 — RAG Real (2 stories, ~3h)

### S-08 RAG adapters — sentence-transformers + Qdrant

**Type:** Technical
**Jira Type:** Task
**Priority:** High
**Complexity:** Small
**Phase:** Phase 3 — RAG Real
**Labels:** `rag`, `phase-3`, `adapters`

#### Description
As a engenheiro de RAG, eu quero adapters para embeddings (sentence-transformers local) e vector store (Qdrant), atrás de protocols, para que retrieve node use abstração e a narrativa "trocar pra Voyage/Bedrock é uma linha" se sustente.

#### Acceptance Criteria
- [ ] Given EmbeddingProvider protocol + SentenceTransformerProvider impl, when embed(["texto"]) é chamado, then retorna lista de vetores de dimensão correta
- [ ] Given VectorStore protocol + QdrantStore impl, when upsert([(id, vector, metadata)]) é chamado e depois search(query_vector, top_k=3), then retorna 3 chunks ranqueados
- [ ] Given `multilingual-e5-small`, when usado, then aplica prefixos `query:` e `passage:` corretamente
- [ ] Given Qdrant container, when start_collection() é chamado, then coleção é criada com config correta (dimensão = 384, cosine)

#### Technical Notes
- `guardrails/adapters/embeddings.py`: `EmbeddingProvider` protocol + `SentenceTransformerProvider` (modelo `intfloat/multilingual-e5-small`, ~120MB)
- `guardrails/adapters/vectorstore.py`: `VectorStore` protocol + `QdrantStore` (qdrant-client)
- Modelo singleton 1x no startup
- ADR 005 documenta sentence-transformers vs Voyage trade-off

#### Dependencies
- Blocks: S-09

---

### S-09 Banking corpus generation + Qdrant ingestion

**Type:** Feature
**Jira Type:** Story
**Priority:** High
**Complexity:** Medium
**Phase:** Phase 3 — RAG Real
**Labels:** `rag`, `phase-3`, `corpus`

#### Description
As a chatbot bancário, eu quero 8 docs sintéticos PT-BR sobre produtos do banco fictício, ingeridos em Qdrant via script, para que (a) Beat 1 da demo (pergunta sobre cartão Gold) tenha doc real pra retornar, e (b) Beat 4 (recomendação financeira) tenha contexto que tente o LLM a violar R2.

#### Acceptance Criteria
- [ ] Given `scripts/generate_corpus.py` executado, when termina, then `docs/banking/` tem 8 arquivos `.md` (incluindo cartao_gold.md e produtos_investimento.md)
- [ ] Given `scripts/ingest.py` rodado, when termina, then Qdrant tem coleção "banking" populada com chunks dos 8 docs
- [ ] Given retrieve node substituído (mock removido), when chamado com query "taxas do cartão Gold", then top-1 chunk é do `cartao_gold.md`
- [ ] Given query "investir 10 mil reais", when retrieve chamado, then top-3 inclui chunk de `produtos_investimento.md` mencionando CDB Premium (necessário pra Beat 4)
- [ ] Given pergunta sobre tema fora do escopo (ex: "qual presidente do Brasil"), when retrieve chamado, then chunks retornados são todos sobre banco (similaridade baixa mas top-k retorna algo)

#### Technical Notes
- `scripts/generate_corpus.py`: chama Claude pra gerar 8 docs em PT-BR (~300 palavras cada) sobre produtos do banco fictício
- 8 docs: cartao_gold, cartao_platinum, conta_corrente, conta_poupanca, pix, emprestimo_pessoal, financiamento, **produtos_investimento** (este precisa mencionar CDB Premium explicitamente para Beat 4)
- `scripts/ingest.py`: chunking por parágrafo (~300 tokens), sem overlap; embed via SentenceTransformerProvider; upsert no QdrantStore
- Substituir mock no retrieve node em `guardrails/pipeline/nodes.py`
- Sanity check inline: print top-1 pra query "cartão Gold"

#### Dependencies
- Blocked by: S-08
- Blocks: S-12 (Docker — init container roda ingest)

---

## Phase 4 — Polish + Ship (6 stories, ~4h)

### S-10 Adversarial test suite from external sources

**Type:** Technical
**Jira Type:** Task
**Priority:** High
**Complexity:** Medium
**Phase:** Phase 4 — Polish + Ship
**Labels:** `tests`, `phase-4`, `adversarial`, `building-rigorously`

#### Description
As a engenheiro de rigor (building-rigorously.md §1), eu quero suite adversarial com fixtures de fontes EXTERNAS (JailbreakBench, HateBR, RealToxicityPrompts) — distintas do autor do matcher — para que taxa de bloqueio reportada não seja medida tautológica, e a entrevista tenha narrativa sólida de validação anti-loop-fechado.

#### Acceptance Criteria
- [ ] Given `scripts/translate_fixtures.py` rodado, when termina, then `tests/adversarial/fixtures/jailbreak.jsonl` tem 20-30 prompts (10-15 EN do JailbreakBench + 10-15 traduzidos via Claude)
- [ ] Given fixtures de tox, then `toxic.jsonl` tem 20-30 prompts (mix HateBR + RealToxicityPrompts)
- [ ] Given fixtures de PII e compliance, then ambos `.jsonl` com 15-20 prompts hand-crafted + flag de loop fechado declarada em LIMITATIONS.md
- [ ] Given `pytest tests/adversarial/`, when executado, then assert taxa-mínima de bloqueio ≥80% nos prompts externos (jailbreak, toxic)
- [ ] Given resultado da suite, when gerado relatório, then escreve em `LIMITATIONS.md` tabela substring-only % vs substring+DeBERTa % no jailbreak (building-rigorously.md §6)

#### Technical Notes
- `scripts/translate_fixtures.py`: Claude traduz prompts EN→PT-BR; persiste JSONL com `{prompt, source, expected_block: bool}`
- Datasets HF: `datasets.load_dataset("JailbreakBench/JBB-Behaviors", ...)`, `ruanchaves/hatebr`, `allenai/real-toxicity-prompts`
- `tests/adversarial/test_jailbreak_adv.py`: loop sobre fixtures, chama validator, compara com `expected_block`, asserta taxa
- ≥1 teste `xfail` documentando bypass conhecido (building-rigorously.md §7)

#### Dependencies
- Blocked by: S-01, S-02, S-03, S-04
- Blocks: S-13 (CI roda adversarial smoke)

---

### S-11 Streamlit client com diagnostics UX

**Type:** Feature
**Jira Type:** Story
**Priority:** Medium
**Complexity:** Small
**Phase:** Phase 4 — Polish + Ship
**Labels:** `ui`, `phase-4`, `streamlit`, `demo`

#### Description
As a avaliador da demo, eu quero Streamlit com histórico de mensagens, badges de OK/BLOCKED, e diagnostics visíveis (category, score, rule_violated, latency breakdown), para que os 4 beats da demo sejam visualmente impactantes e a narrativa de "guardrail bidirecional" seja autoexplicativa.

#### Acceptance Criteria
- [ ] Given Streamlit rodando, when usuário envia mensagem benigna, then aparece badge verde "OK" + latency breakdown collapsible
- [ ] Given mensagem com PII, when bloqueada, then badge vermelha "BLOCKED pii_input", entidade detectada, mensagem de fallback
- [ ] Given Beat 4 (input inocente, output viola R2), when bloqueado, then badge "BLOCKED compliance R2", reasoning do judge visível
- [ ] Given histórico de mensagens, when usuário rola pra cima, then todos os turnos anteriores estão visíveis com seus respectivos diagnostics

#### Technical Notes
- `ui/streamlit_app.py`: 1 arquivo único; chama API via `requests` (URL `http://api:8000/chat` em Docker)
- Session state pra histórico
- Cores: verde (OK), amarelo (warning não usado), vermelho (BLOCKED)
- Badge mostra `category` + `rule_violated` quando aplicável
- Collapsible mostra `diagnostics` JSON formatado

#### Dependencies
- Blocked by: S-07
- Blocks: S-12 (Docker — ui service)

---

### S-12 Docker compose stack

**Type:** Technical
**Jira Type:** Task
**Priority:** High
**Complexity:** Medium
**Phase:** Phase 4 — Polish + Ship
**Labels:** `infra`, `phase-4`, `docker`

#### Description
As a avaliador externo, eu quero `docker compose up` levantar api + ui + qdrant + ingest init container em <3min em máquina limpa, para que a demo seja reprodutível sem instruções complicadas de setup.

#### Acceptance Criteria
- [ ] Given máquina limpa com `.env` preenchido (ANTHROPIC_API_KEY), when `docker compose up`, then 4 services sobem (api, ui, qdrant, init-ingest)
- [ ] Given init container, when termina, then Qdrant tem corpus ingerido (volume persistido) antes da API responder
- [ ] Given build de imagens, when `docker compose build`, then api.Dockerfile e ui.Dockerfile compilam sem erro
- [ ] Given containers rodando, when `curl http://localhost:8000/health`, then 200 com validators_loaded
- [ ] Given Streamlit em `http://localhost:8501`, when aberto, then UI conecta na API e funciona
- [ ] Given containers, then api roda como user não-root

#### Technical Notes
- `docker/api.Dockerfile`: multi-stage (builder com uv install, runtime slim Python 3.12); pre-baixa modelos HF (DeBERTa + sentence-transformers) na image
- `docker/ui.Dockerfile`: slim Python + streamlit
- `docker-compose.yml`: services api, ui, qdrant, ingest (depends_on com healthcheck)
- Volume persistente pra Qdrant data
- Network bridge pros services se enxergarem

#### Dependencies
- Blocked by: S-07, S-09, S-11
- Blocks: S-13 (CI builda imagens), S-15 (rehearsal precisa compose funcional)

---

### S-13 GitHub Actions CI

**Type:** Technical
**Jira Type:** Task
**Priority:** Medium
**Complexity:** Small
**Phase:** Phase 4 — Polish + Ship
**Labels:** `ci`, `phase-4`, `github-actions`

#### Description
As a avaliador inspecionando o repo, eu quero workflow GitHub Actions verde rodando lint + testes unit + adversarial smoke + docker build em cada push/PR, para que CI seja narrativa concreta de LLMOps e suite adversarial seja vista rodando.

#### Acceptance Criteria
- [ ] Given push na main, when workflow dispara, then 4 jobs rodam: ruff lint, pytest unit, pytest adversarial (smoke ≥10 prompts/categoria), docker build
- [ ] Given workflow concluído, when verde, then aparece check verde no GitHub
- [ ] Given workflow runs page, when avaliador abre, then vê histórico de runs com tempos
- [ ] Given adversarial smoke, when roda no CI, then NÃO precisa de ANTHROPIC_API_KEY (mocka chamadas Claude OU pula testes que exigem network)

#### Technical Notes
- `.github/workflows/ci.yml`: 4 jobs (paralelos quando possível)
- Cache de uv lockfile e modelos HF pra acelerar
- adversarial smoke = subset reduzido (não roda 30 prompts/categoria; só 10)
- Para Compliance Judge: mock Anthropic SDK no CI (sem custo); judge real só local

#### Dependencies
- Blocked by: S-10, S-12
- Blocks: nenhum (mas Relates to S-15)

---

### S-14 Documentation — README + LIMITATIONS + ADRs

**Type:** Technical
**Jira Type:** Task
**Priority:** Medium
**Complexity:** Small
**Phase:** Phase 4 — Polish + Ship
**Labels:** `docs`, `phase-4`, `building-rigorously`

#### Description
As a avaliador da entrevista, eu quero README claro com roteiro de demo 8min, LIMITATIONS.md com ≥8 gaps confirmados, e ADRs curtas pra decisões críticas, para que a credibilidade seja construída via honestidade técnica (building-rigorously.md §7) em vez de discurso de marketing.

#### Acceptance Criteria
- [ ] Given clone do repo, when usuário lê README, then segue setup em <5min e roda `docker compose up`
- [ ] Given LIMITATIONS.md, then lista ≥8 itens CONFIRMADOS (não hipotéticos): PII sem checksum, sem CNPJ, sem nome/endereço, Compliance Judge fixtures loop fechado, substring matching limits, Langfuse cortado, Voyage cortado, sem auth, sem rate limit
- [ ] Given pasta `adr/`, then contém 4-5 ADRs <300 palavras cada: 001-pivot-guardrails-ai, 002-langgraph-orchestration, 003-json-logs-over-langfuse, 004-sentence-transformers-over-voyage, 005-regex-only-pii-no-presidio, 006-compliance-judge-rubric
- [ ] Given README, then inclui tabela de bloqueio substring-only vs substring+DeBERTa (gerada pela adversarial suite)

#### Technical Notes
- `README.md`: overhaul completo (atual é boilerplate); seções: Visão, Arquitetura, Setup, Demo 8min, Tests, LIMITATIONS
- `LIMITATIONS.md`: novo arquivo
- `adr/0XX-*.md`: padrão Michael Nygard (Context, Decision, Consequences)
- `CLAUDE.md` já foi atualizado no commit anterior — não precisa tocar de novo

#### Dependencies
- Pode rodar em paralelo com qualquer outra story após S-09 (precisa do corpus pra documentar)

---

### S-15 Demo rehearsal cronometrado + backup

**Type:** Technical
**Jira Type:** Task
**Priority:** High
**Complexity:** Small
**Phase:** Phase 4 — Polish + Ship
**Labels:** `demo`, `phase-4`, `rehearsal`

#### Description
As a candidato indo pra entrevista, eu quero ter rehearsal cronometrado da demo 8min em máquina limpa + vídeo de backup gravado + requests httpie/curl prontos como files, para que se algo travar ao vivo eu tenha fallback e não dependa de internet/rede da empresa.

#### Acceptance Criteria
- [ ] Given setup limpo (`docker compose down -v && docker compose up`), when demo é executada 3x consecutivas, then 4 beats funcionam consistente (sem flakiness no Beat 4)
- [ ] Given Beat 4 testado com 5+ rephrasings da pergunta de investimento, when judge é chamado, then bloqueia em ≥4 dos 5 (sensibilidade aceitável)
- [ ] Given vídeo de backup, when gravado, then mostra demo completa funcionando em <8min
- [ ] Given requests prontos, then arquivos `demo/01-happy.http`, `demo/02-jailbreak.http`, `demo/03-pii.http`, `demo/04-compliance.http` existem com curl/httpie equivalente
- [ ] Given tempo total da demo, when cronometrado, then ≤8min

#### Technical Notes
- Se Beat 4 falhar em rephrasings: tunar few-shots do R2 no `rubric.py` ou ajustar system prompt do chatbot
- Plano B Beat 4: trocar pra R3 (cliente pede "transfira" → bot diz "vou transferir") — mais simples de induzir
- Vídeo: OBS ou screen recording nativo do OS

#### Dependencies
- Blocked by: S-12 (precisa do docker-compose), S-13 (precisa do CI verde)
- Relates to: tudo

---

## Dependency Graph (resumido)

```
Phase 1:  S-01 ─┐
          S-02 ─┤
          S-03 ─┼─▶ S-06 ─▶ S-07 ─┐
          S-04 ─┘                  │
          S-05 ──▶ S-06            │
                                   │
Phase 3:  S-08 ─▶ S-09 ────────────┤
                                   │
Phase 4:  S-01-04 ─▶ S-10          │
                     │             │
          S-07, S-09, S-11 ─▶ S-12 ┤
          S-11 ◀── S-07            │
          S-10, S-12 ─▶ S-13       │
                                   │
          S-09 ─▶ S-14             │
                                   │
          S-12, S-13 ─▶ S-15 ◀─────┘
```

---

## Coverage check vs PRD §11 (Success Criteria)

| Critério do PRD | Stories que cobrem |
|---|---|
| `docker compose up` em <3min | S-12 |
| `curl POST /chat` benigno <3s p50 | S-07, S-06 |
| 4 ataques demo bloqueados | S-01 (tox), S-02 (pii), S-03 (jailbreak), S-04 (compliance) + S-15 (rehearsal) |
| Streamlit diagnostics | S-11 |
| Suite adversarial ≥80% | S-10 |
| Compliance Judge ≥90% fixtures | S-10 (assertion) + S-04 (impl) |
| CI verde | S-13 |
| Logs JSON via `docker logs api | jq` | S-05 |
| LIMITATIONS ≥8 itens | S-14 |
| ≥4 ADRs | S-14 |
| CLAUDE.md atualizado | já feito (commit 2b71db0) |
| ≥1 xfail | S-10 |
| Tabela layered defense | S-10 + S-14 |
| Demo cabe em 8min | S-15 |
