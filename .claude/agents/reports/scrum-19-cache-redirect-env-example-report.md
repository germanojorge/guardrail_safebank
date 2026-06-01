# Implementation Report

**Plan**: `.claude/agents/plans/scrum-19-cache-redirect-env-example.plan.md`
**Branch**: `main`
**Status**: COMPLETE

## Summary

Implementação do módulo `guardrails/env_bootstrap.py` para carregar `.env` e derivar automaticamente caches HF (`HF_HOME`, `HF_DATASETS_CACHE`, `HF_HUB_CACHE`, `TRANSFORMERS_CACHE`) e `TMPDIR` a partir de `ML_CACHE_ROOT`. Criação do `.env.example` commitado documentando todas as variáveis de cache, segredos e runtime. Autoload do bootstrap no `conftest.py` raiz e nos scripts que chamam `load_dataset()`, garantindo que as env vars estejam setadas antes do import de `datasets`/`transformers`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Criar módulo de bootstrap de ambiente | `guardrails/env_bootstrap.py` | ✅ |
| 2 | Adicionar `python-dotenv` às dependências | `pyproject.toml` | ✅ |
| 3 | Autoload no conftest raiz | `conftest.py` | ✅ |
| 4 | Patchar scripts que chamam `load_dataset()` | 5 scripts | ✅ |
| 5 | Criar `.env.example` | `.env.example` | ✅ |
| 6 | Documentar no README | `README.md` | ✅ |
| 7 | Verificar `.gitignore` | `.gitignore` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Bootstrap deriva caches de `ML_CACHE_ROOT` | ✅ |
| Lint (`ruff check`) | ✅ |
| Format (`ruff format --check`) | ✅ |
| `.env.example` parseia sem erro | ✅ |
| `.env.example` não vaza segredos | ✅ |
| gitignore correto (`.env` ignorado, `.env.example` versionado) | ✅ |
| Smoke pytest adversarial `--collect-only` | ✅ (82 testes coletados) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `guardrails/env_bootstrap.py` | CREATE | +64 |
| `.env.example` | CREATE | +53 |
| `conftest.py` | UPDATE | +6 / −1 |
| `pyproject.toml` | UPDATE | +1 |
| `README.md` | UPDATE | +24 |
| `scripts/ingest_itau_faq.py` | UPDATE | +1 |
| `scripts/build_jailbreak_index.py` | UPDATE | +1 |
| `scripts/build_outofscope_seeds.py` | UPDATE | +1 |
| `scripts/screen_realtoxicityprompts.py` | UPDATE | +1 |
| `scripts/finetune_itau_embedding.py` | UPDATE | +1 |
| `.gitignore` | UPDATE | +1 |

## Deviations from Plan

1. **Conftest sem `sys.path.insert` prévio**: O `conftest.py` original não tinha inserção do root no `sys.path`. O plano mencionava "depois de inserir o root no sys.path (linha 8)". Como o `conftest.py` real não tinha isso, adicionei o `sys.path.insert(0, str(Path(__file__).parent))` antes do import do bootstrap para garantir que o pacote `guardrails` seja resolvido corretamente durante a execução do pytest.

2. **Resiliência a `.env` malformado e permissão negada**: O env_bootstrap original do plano não previa dois cenários reais encontrados:
   - O `.env` real do usuário continha uma linha malformada (sem newline entre `ML_CACHE_ROOT` e `LLM_PROVIDER`), o que fazia o `python-dotenv` emitir warning e potencialmente falhar. Adicionei `try/except` em torno do `load_dotenv()` para capturar erros de parsing e continuar com warning.
   - O `ML_CACHE_ROOT` apontava para um HD externo não montado/sem permissão de escrita (`/run/media/germano/...`), causando `PermissionError` no `mkdir`. Adicionei `try/except OSError` no loop de criação de diretórios para que o bootstrap não quebre se não conseguir criar os diretórios (o HF/uv criam sob demanda depois).

3. **Ruff format no env_bootstrap.py**: Após a criação do arquivo, o `ruff format --check` indicou que o arquivo precisava ser formatado. Rodei `uv run ruff format guardrails/env_bootstrap.py` e a validação passou.

## Tests Written

Nenhum teste novo foi escrito. O plano não exigia testes unitários para o módulo de infraestrutura `env_bootstrap`; a validação foi feita via:
- Smoke do harness (`pytest --collect-only`)
- Verificação manual de derivação de env vars com `ML_CACHE_ROOT=/tmp/ml-cache-test`
- Lint e format checks

---

*Relatório gerado automaticamente após implementação do plano SCRUM-19.*
