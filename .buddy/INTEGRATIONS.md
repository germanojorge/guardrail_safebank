🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# External Integrations

Tudo que o projeto conversa de fora pra dentro.

| Serviço | Pra que serve | Onde está configurado |
|---|---|---|
| **Anthropic API** (Claude Sonnet 4.6 + Haiku 4.5) | Chatbot e Compliance Judge | `guardrails/adapters/llm.py` (AnthropicProvider) · model em `config.yaml` · env `ANTHROPIC_API_KEY` |
| **Qdrant** (Docker) | Vector store para RAG | `guardrails/adapters/vector_store.py` (QdrantStore) · `config.yaml` (`qdrant.host`, `qdrant.collection`) · env `QDRANT_HOST`, `QDRANT_COLLECTION` |
| **HuggingFace Hub** | Download de modelos (Prompt-Guard-2 *gated*, detoxify, e5-small) | env `HF_TOKEN`, `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` no `docker-compose.yml` |
| **HuggingFace Datasets** | Itaú FAQ ingestion + adversarial fixtures (HateBR, RealToxicityPrompts) | `scripts/ingest_itau_faq.py`, `scripts/screen_hatebr.py`, `scripts/screen_realtoxicityprompts.py` |
| **spaCy `pt_core_news_lg`** | NER e POS tagging PT-BR (jailbreak + Presidio NER) | Baixado no `docker/Dockerfile.models` |
| **Redis** (declarado em deps) | Não usado no path crítico — declarado para Extras | `pyproject.toml` (sem serviço no compose) |
| **GitHub Actions** | CI: lint, test, adversarial smoke, docker build, demo smoke (manual) | `.github/workflows/ci.yml` |

## Endpoints HTTP expostos

| Método | Rota | Pra que serve |
|---|---|---|
| POST | `/chat` | Caminho principal: input guard → RAG → LLM → output guard |
| POST | `/v1/guard/output` | Aplica só o output guard num texto arbitrário (usado pela demo PII de saída) |
| GET | `/health` | Liveness + status de modelos carregados |

## Variáveis de ambiente

| Nome | Pra que serve | Default | Onde aparece |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Chave da Anthropic | — (obrigatória, salvo em modo mock) | `docker-compose.yml`, `config.yaml` |
| `HF_TOKEN` | Token HuggingFace (Prompt-Guard-2 é repo gated) | — | `docker-compose.yml`, scripts de ingest |
| `LLM_PROVIDER` | `anthropic` ou `mock` | `anthropic` | `guardrails/api/app.py` (factory) |
| `QDRANT_HOST` | Host do Qdrant | `qdrant` (dentro do compose) | `config.yaml`, `docker-compose.yml` |
| `QDRANT_COLLECTION` | Nome da coleção do vector store | `itau_faq` | `docker-compose.yml`, scripts |
| `ML_CACHE_ROOT` | Pasta host para cache HF/torch (montada read-only) | `/run/media/germano/Novo volume/Linux/ml-cache` | `docker-compose.yml` |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | Força uso do cache local em runtime | `1` no compose | `docker-compose.yml` |

## Segredos

- **Nunca** ficam no repo. Vão num `.env` na raiz (no `.gitignore`) ou são exportados na shell antes do `docker compose up`.
- O CI usa GitHub Secrets: `ANTHROPIC_API_KEY` (job `demo-smoke` apenas, manual via `workflow_dispatch`).
- Logs JSON do structlog **não** logam o texto cru — usam `input_hash` (sha256) para correlacionar sem vazar PII.
