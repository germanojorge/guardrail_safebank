🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Open Questions

> Coisas que o Buddy não conseguiu inferir só do repo. Ajude a preencher!

## 1. ADR 005 vs realidade do código

- **Pergunta:** o ADR 005 diz "regex puro, sem Presidio". Mas `guardrails/api/app.py` instancia `_build_presidio_engine()` e passa pro `PIIValidator`. Qual é a fonte da verdade hoje?
- **Onde investigar:** `guardrails/validators/pii.py` (procurar `presidio_engine`), `adr/005-regex-pii-no-presidio.md`, commit `e38468b` ("Presidio NER + checksums").
- **Hipótese do Buddy:** o ADR foi revertido parcialmente — PII real combina regex + Presidio NER PT-BR + checksums. Vale atualizar o ADR ou adicionar um ADR 007.

## 2. Coleção Qdrant default

- **Pergunta:** o `docker-compose.yml` usa `QDRANT_COLLECTION=itau_faq` por default, mas o `config.yaml` tem `collection: "banking_kb"`. Qual ganha em runtime?
- **Onde investigar:** `guardrails/config.py` (precedência env vs YAML), `guardrails/adapters/vector_store.py`.

## 3. Knowledge base reorganizada (uncommitted)

- **Pergunta:** os arquivos em `data/banking_kb/` foram renumerados (01_cartao_gold → 01_pix_doc, etc.) mas a mudança não foi commitada. É WIP intencional?
- **Onde investigar:** `git status`, `git diff data/banking_kb/`.

## 4. Streamlit como dependência opcional

- **Pergunta:** `streamlit` é `optional-dependency` em `pyproject.toml`, mas o `docker/Dockerfile.ui` precisa dele. Como o build instala?
- **Onde investigar:** `docker/Dockerfile.ui`.

## 5. Cache ML hardcoded ao HD externo do dono

- **Pergunta:** `ML_CACHE_ROOT` default = `/run/media/germano/Novo volume/Linux/ml-cache`. Qualquer outro contributor que clonar o repo vai falhar ao subir o compose. Vale tornar opcional ou documentar exigência?
- **Onde investigar:** `docker-compose.yml`, `.env.example` (não existe).

## 6. `redis` declarado mas não usado

- **Pergunta:** `redis>=7.4.0` está em `pyproject.toml`. Não vejo serviço Redis no compose nem importações em `guardrails/`. Era pra alguma feature de Extras (rate limit? cache de embeddings?). Remover ou usar?
