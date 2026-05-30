🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Entry Points

> Onde a execução começa. Verificado contra `pyproject.toml`, `docker-compose.yml`, `docker/`.

## HTTP (FastAPI)

| Entry | Arquivo | O que faz |
|---|---|---|
| `guardrails-api` script | `guardrails/api/app.py:run` | `uvicorn` factory; lifespan carrega validators + compila o LangGraph |
| `POST /chat` | `guardrails/api/app.py` | Pipeline completo (input guard → RAG → LLM → output guard) |
| `POST /v1/guard/output` | `guardrails/api/app.py` | Aplica só o output guard num texto arbitrário (demo PII de saída) |
| `GET /health` | `guardrails/api/app.py` | Liveness + status de modelos carregados (`ModelsLoaded` schema) |

## UI

| Entry | Arquivo | O que faz |
|---|---|---|
| Streamlit chat | `ui/streamlit_app.py` | UI com diagnósticos coloridos; consome `API_URL` (default `http://api:8000`) |

## Containers (`docker-compose.yml`)

| Serviço | Comando | Pra que |
|---|---|---|
| `qdrant` | `qdrant/qdrant:latest` | Vector store (porta 6333) |
| `api` | uvicorn via `docker/Dockerfile.api` | API principal (porta 8000) |
| `ui` | streamlit via `docker/Dockerfile.ui` | Cliente (porta 8501) |
| `ingest` | `python scripts/ingest_banking_kb.py` (perfil `ingest`) | Popular Qdrant com `data/banking_kb/` |
| `ingest_itau` | `python scripts/ingest_itau_faq.py` (perfil `ingest`) | Popular Qdrant com FAQ Itaú do HF |

## CLIs / scripts úteis

| Script | Pra que |
|---|---|
| `scripts/ingest_banking_kb.py` | Ingestão do KB sintético (8 docs MD) |
| `scripts/ingest_itau_faq.py` | Ingestão do dataset `Itau-Unibanco/FAQ_BACEN` |
| `scripts/build_jailbreak_index.py` | Constrói `data/jailbreak_index.npz` (seeds semânticas) |
| `scripts/build_outofscope_seeds.py` | Gera `data/out_of_scope_seeds.json` |
| `scripts/measure_jailbreak_layers.py` | Mede contribuição de cada camada do jailbreak validator |
| `scripts/finetune_itau_embedding.py` | Fine-tuning do embedder em pares Itaú |
| `scripts/screen_hatebr.py` / `screen_realtoxicityprompts.py` | Filtra fixtures adversariais |
| `scripts/translate_fixtures.py` | Traduz fixtures EN → PT-BR via Claude |
| `demo/scripts/auto_demo.py` | Robô que executa os 4 beats em sequência |
| `demo/scripts/consistency_test.py` | Roda a demo 3× e checa flakiness |
| `demo/scripts/test_beat4.py` | Sensitivity test do Beat 4 (≥80% block rate) |
| `demo/chat_cli.py` | Cliente CLI interativo (alternativa ao Streamlit) |

## Testes

| Comando | Cobertura |
|---|---|
| `uv run pytest -m "not slow and not network"` | Unit tests, sem modelos pesados, sem rede |
| `uv run pytest -m adversarial` | Suite adversarial (carrega modelos) |
| `uv run pytest -m "adversarial and network"` | Inclui o Compliance Judge real (Anthropic) |
