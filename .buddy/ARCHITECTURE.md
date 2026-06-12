🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Architecture

> **Verificado** contra `guardrails/pipeline/graph.py`, `guardrails/api/app.py`, `config.yaml`, `README.md` e os 6 ADRs em `adr/`.

## Visão geral

O sistema é um **proxy bidirecional** que fica na frente de um chatbot bancário Claude. Toda mensagem do cliente passa por um **input guard** (validators que checam toxicidade, PII, jailbreak, fora-de-escopo). Se passar, vai pro **retrieve** (RAG no Qdrant) → **generate** (Claude Sonnet) → **output guard** (validators de saída: toxic, PII, compliance). Se qualquer guard falhar, vai pro nó **block_log** que persiste o evento em JSON e retorna `blocked=true` com HTTP 200 (decisão de política, não erro).

A orquestração é um `StateGraph` do LangGraph com 5 nós e arestas condicionais. Validators são **funções Python puras** (sem herança de framework). A única chamada LLM dentro de um validator é o **Compliance Judge** (Claude Haiku com rubrica R1–R5 e tool_use).

## Componentes principais

| Componente | Onde mora | Responsabilidade |
|---|---|---|
| FastAPI proxy | `guardrails/api/app.py` | Endpoints `POST /chat`, `POST /v1/guard/output`, `GET /health`; lifespan carrega modelos uma vez; `_create_components` é o factory que CI/testes monkeypatcham |
| Schemas | `guardrails/api/schemas.py` | `ChatRequest`, `ChatResponse`, `Diagnostics`, `LatencyBreakdown` (pydantic) |
| Pipeline graph | `guardrails/pipeline/graph.py` | `build_graph()` monta o StateGraph com 5 nós: `input_guard → retrieve → generate → output_guard → block_log/END` |
| Pipeline nodes | `guardrails/pipeline/nodes.py` | Funções que executam cada estágio e atualizam `GraphState` |
| Pipeline state | `guardrails/pipeline/state.py` | `GraphState` TypedDict + `SEVERITY_MAP` |
| Validators | `guardrails/validators/` | `toxic`, `pii`, `jailbreak`, `compliance`, `compliance_rules` (mock), `out_of_scope` |
| Detectores (regras) | `guardrails/detectors/` | `data_leak`, `financial_advice`, `fraud`, `out_of_scope` — usados pelo `RuleBasedComplianceValidator` no modo mock |
| Compliance rubric | `guardrails/compliance/rubric.py` + `prompt.py` | Regras R1–R5 e prompt few-shot do judge Haiku |
| Adapters | `guardrails/adapters/` | `llm.py` (AnthropicProvider), `embedding.py` (SentenceTransformerProvider), `vector_store.py` (QdrantStore) — todos atrás de Protocols pra trocar de provider |
| Observabilidade | `guardrails/observability/logger.py` | `setup_logging()` configura structlog JSON; `request_id` UUID4 via `contextvars` |
| Config | `guardrails/config.py` + `config.yaml` | Pydantic-settings com expansão de `${ENV_VAR}` |
| PII patterns | `guardrails/_pii_patterns.py` | Regex compilados (email, telefone, CPF, cartão 16 dígitos) |

## Fluxo de uma requisição (request flow)

1. Cliente faz `POST /chat` com `{"message": "..."}`.
2. FastAPI middleware liga o `request_id` (UUID4) no contexto do structlog.
3. Pipeline entra no nó **`input_guard`**:
   - Roda em ordem: `toxic`, `pii_input`, `out_of_scope`, `jailbreak`.
   - Se algum bloquear, `state["blocked"] = True` e a aresta condicional manda pro `block_log`.
4. Senão, **`retrieve`** consulta Qdrant (coleção `itau_faq`, FAQ BACEN Itaú).
5. **`generate`** chama `AnthropicProvider.chat()` (Claude Sonnet 4.6) com system prompt + chunks RAG + mensagem.
6. **`output_guard`** roda em ordem: `toxic`, `pii_output`, `compliance` (Haiku judge — só este nó é assíncrono e custa rede).
7. Se algum guard de saída bloquear → `block_log`. Senão → `END` e a resposta volta com `blocked=false`.
8. Em qualquer bloqueio, structlog emite um evento `guardrail.blocked` com `category`, `severity`, `rule_violated`, `input_hash`, `latency_ms` por estágio.

## Defesa em camadas no jailbreak

O `JailbreakValidator` (`guardrails/validators/jailbreak.py`) combina **4 camadas**, configurável em `config.yaml`:

1. **Substring fast-path** — keyword match (rápido, alta precisão, baixa cobertura)
2. **Prompt-Guard-2** (`meta-llama/Llama-Prompt-Guard-2-86M`) — classifier HF multilíngue, threshold 0.85
3. **POS tagger** — análise sintática via spaCy `pt_core_news_lg` (`use_pos_tagger: true`, threshold 0.55)
4. **Semantic similarity** — embedding match contra seed bank em `data/jailbreak_index.npz` (`use_semantic: true`, threshold 0.80)

A contribuição de cada camada por classe de ataque está em `LIMITATIONS.md`.

## Compliance Judge (LLM-as-Judge)

- Único validator que chama LLM (Claude Haiku 4.5, timeout 5s).
- Rubrica fixa de 5 regras (R1–R5) com 2 few-shots por regra — ver `guardrails/compliance/rubric.py`.
- Saída estruturada via **tool_use** do Anthropic SDK: `{verdict, rule_violated, reasoning}`.
- **Bloqueio direto** (sem reask) — reask vira Extras no roadmap.
- No modo `LLM_PROVIDER=mock`, substituído pelo `RuleBasedComplianceValidator` (combina os 4 detectores rule-based em `guardrails/detectors/`).

## Fronteiras-chave

- **Validators não conhecem LangGraph.** São funções `(text) -> ValidatorResult`. Permite testar unitariamente sem o grafo.
- **Adapters Protocol** isolam Anthropic, Qdrant e sentence-transformers. Troca de provider (ex: Bedrock) é mudança local.
- **Single uvicorn worker** porque modelos pesam ~1.5 GB e não devem ser duplicados.
- **`_create_components` factory** isolado da `lifespan` permite que testes patchem todos os componentes com um único `monkeypatch`.
- **Block é HTTP 200**, não 4xx — bloqueio é decisão de política, não erro do cliente.

## ADRs (Architecture Decision Records)

Decisões formalmente documentadas em `adr/`:

| ADR | Decisão |
|---|---|
| 001 | Abandonar a biblioteca `guardrails-ai` |
| 002 | LangGraph standalone (sem LangChain) |
| 003 | Compliance Judge = Claude Haiku + tool_use |
| 004 | Jailbreak em camadas (substring + DeBERTa/Prompt-Guard-2 + POS + semântico) |
| 005 | PII via regex puro (Presidio fica como Extras; presente como opcional no código) |
| 006 | Embeddings locais (sentence-transformers) em vez de Voyage AI |

> ℹ️ ADR 005 vs realidade: o código `guardrails/api/app.py` já instancia `_build_presidio_engine()` — o ADR foi parcialmente revertido. PII no MVP é **regex + Presidio NER opcional**. Ver `NOTES/open_questions.md`.
