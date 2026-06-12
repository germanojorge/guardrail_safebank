🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Repo Map

> Tour por pasta. Verificado em 2026-05-29 contra `HEAD = 189773c`.

## Top-level

| Pasta | Pra que serve | Começa por aqui? |
|---|---|---|
| `guardrails/` | Pacote Python principal (API, pipeline, validators, adapters) | **Sim** |
| `tests/` | Testes pytest: `unit/`, `adversarial/`, `api/`, `fixtures/` | Depois de `guardrails/` |
| `scripts/` | Ingestão (FAQ Itaú), build de índices, screening de fixtures, medição de camadas | Quando for popular dados |
| `data/` | Splits congelados de eval (`data/eval/`) + índices/seeds (gerados) | Pra entender o RAG |
| `demo/` | Roteiro da demo de 8 min: `.http`, `.sh`, robô auto, `WALKTHROUGH.md` | Pra ver o produto rodando |
| `docker/` | 3 Dockerfiles: `Dockerfile.api`, `Dockerfile.ui`, `Dockerfile.models` (base com modelos) | Pra mudar build |
| `adr/` | 6 Architecture Decision Records (001–006) | Pra entender *por que* decisões |
| `ui/` | Streamlit (`streamlit_app.py`) — cliente com diagnósticos coloridos | Pra mudar UI |
| `slides/` | Slides da apresentação técnica | Não é código |
| `.github/workflows/` | Pipeline CI (lint, test, adversarial, docker-build, demo-smoke) | Quando ajustar CI |
| `.claude/` | Agentes/PRDs/skills do Claude Code (PRD v2.0, plano, etc.) | Contexto histórico |
| `.buddy/` | Esta knowledge base | Você está aqui |

## Dentro de `guardrails/`

| Subpasta | Conteúdo |
|---|---|
| `api/` | `app.py` (FastAPI + lifespan + `_create_components`), `schemas.py` (pydantic IO) |
| `pipeline/` | `graph.py` (build_graph), `nodes.py` (5 nós), `state.py` (GraphState TypedDict) |
| `validators/` | `base.py` (ValidatorResult), `toxic`, `pii`, `jailbreak`, `out_of_scope`, `compliance`, `compliance_rules` |
| `detectors/` | Detectores rule-based PT-BR: `data_leak`, `financial_advice`, `fraud`, `out_of_scope` + `base.py` |
| `compliance/` | `rubric.py` (R1–R5), `prompt.py` (few-shots do Haiku judge) |
| `adapters/` | `llm.py` (AnthropicProvider), `embedding.py` (SentenceTransformerProvider), `vector_store.py` (QdrantStore) |
| `observability/` | `logger.py` (structlog JSON setup) |
| `_pii_patterns.py` | Regex PT-BR (email, telefone, CPF, cartão) |
| `config.py` | pydantic-settings loader pra `config.yaml` |

## Dentro de `tests/`

| Subpasta | Foco |
|---|---|
| `unit/` | 16 arquivos cobrindo cada validator, detector, adapter, config, logger, pipeline |
| `adversarial/` | 4 pipelines (compliance, jailbreak, pii, toxic) + `fixtures/` externas |
| `api/` | `test_chat_endpoint`, `test_health_endpoint`, `test_fail_closed` |
| `fixtures/` | Datasets adversariais (JailbreakBench, HateBR PT, RealToxicityPrompts, hand-crafted PII/compliance) |

## Onde começar a ler código (ordem sugerida)

1. **`README.md` na raiz** — ASCII art da arquitetura e os 4 beats da demo.
2. **`guardrails/api/app.py`** — entry point HTTP, lifespan, factory de componentes.
3. **`guardrails/pipeline/graph.py`** — o StateGraph e suas arestas condicionais.
4. **`guardrails/pipeline/nodes.py`** — o que cada nó faz na prática.
5. **`guardrails/validators/base.py`** — `ValidatorResult` (contrato comum).
6. **`guardrails/validators/compliance.py`** + `guardrails/compliance/rubric.py` — o diferencial do projeto.
7. **`guardrails/validators/jailbreak.py`** — defesa em camadas mais sofisticada.
8. **`config.yaml`** — vê todos os knobs no contexto.
9. **`adr/*.md`** — porquê das decisões (ordem 001 → 006).
10. **`LIMITATIONS.md`** — onde o sistema *sabe* que falha.

## Arquivos canônicos na raiz

| Arquivo | Pra quê |
|---|---|
| `CLAUDE.md` | Briefing do projeto, decisões, tabela requisito-da-vaga × feature |
| `README.md` | README público (inglês, com badges, ASCII e curls da demo) |
| `LIMITATIONS.md` | Gaps confirmados (anti loop fechado — building-rigorously.md §7) |
| `config.yaml` | Configuração runtime |
| `pyproject.toml` | Deps + markers de teste + ruff |
| `docker-compose.yml` | 4 serviços + perfil `ingest` |
| `conftest.py` | Fixtures pytest globais |
