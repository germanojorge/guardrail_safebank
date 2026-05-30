🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Tech Stack

> Verificado contra `pyproject.toml`, `docker-compose.yml`, `config.yaml` e `.github/workflows/ci.yml`.

## Linguagem

- **Python ≥ 3.12** (ver `pyproject.toml`, `.python-version`)
- Gerenciador de ambiente: **uv** (Astral)
- Build backend: **Hatchling**

## Frameworks principais

| Camada | Tecnologia | Versão mínima |
|---|---|---|
| API HTTP | **FastAPI** + uvicorn | 0.115 / 0.34 |
| Orquestração do pipeline | **LangGraph** standalone (sem LangChain) | 0.4 |
| Cliente LLM | **Anthropic SDK** | 0.104.1 |
| Embeddings locais | **sentence-transformers** (`intfloat/multilingual-e5-small`) | 3.0 |
| NLP / NER | **spaCy** (`pt_core_news_lg`) | 3.7 |
| PII NER opcional | **Presidio Analyzer + Anonymizer** | 2.2 |
| PII extra | **GLiNER** | 0.2.26 |
| Toxicidade | **detoxify** (XLM-RoBERTa multilingual) | 0.5.2 |
| Jailbreak ML | **transformers** + `meta-llama/Llama-Prompt-Guard-2-86M` | 4.40 |
| Modelos ML base | **PyTorch** | 2.2 |
| Validação de schema | **Pydantic** + pydantic-settings | 2.10 / 2.7 |
| Logging estruturado | **structlog** (JSON em stdout) | 25.1 |
| UI | **Streamlit** (extra opcional) | 1.41 |
| Vector store client | **qdrant-client** | 1.13 |
| Cache (opcional) | **redis** | 7.4 |
| HTTP cliente | **httpx** | 0.27 |

## Build & package

- `pyproject.toml` define o projeto (`guardrail-safebank`, v0.1.0)
- `uv.lock` (~860 KB) — lockfile reproduzível
- Pacote Python único: `guardrails/` (declarado em `[tool.hatch.build.targets.wheel]`)
- Entry-points: `guardrails-api` (`guardrails.api.app:run`) e `guardrails-ui`

## Testes

- **pytest 8+** com markers: `slow`, `adversarial`, `network`
- **pytest-asyncio** ≥ 0.25
- Estrutura: `tests/unit/`, `tests/adversarial/`, `tests/api/`, `tests/fixtures/`
- Threshold de bloqueio adversarial: **≥80%** (jailbreak e toxicidade)

## Lint / format

- **Ruff 0.15+** (line-length 220, cache em `.cache/ruff`)
- **pre-commit 4.6+** (config em `.pre-commit-config.yaml`)

## Containerização

- **Docker Compose v2** orquestra 4 serviços: `qdrant`, `api`, `ui`, `ingest` (perfil `ingest`)
- Dockerfiles separados: `docker/Dockerfile.api`, `docker/Dockerfile.ui`, `docker/Dockerfile.models` (base de modelos)
- Single uvicorn worker (modelos pesam ~1.5 GB, evita duplicação)

## CI

- **GitHub Actions** (`.github/workflows/ci.yml`)
- Jobs: `lint` (ruff), `test` (pytest sem slow/network), `adversarial-smoke`, `docker-build`, `demo-smoke` (manual, exige `ANTHROPIC_API_KEY`)
- Cache: `setup-uv@v5` com `enable-cache: true` + Docker `cache-from: type=gha`

## Deploy

- **Local only (Docker Compose)** no MVP
- AWS Bedrock / ECS é **roadmap** (ver `adr/` e CLAUDE.md §Extras), apoiado pelo adapter `LLMProvider`
