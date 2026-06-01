# Plan: SCRUM-19 — Redirecionar caches de ML/datasets pro HD externo + `.env.example`

## Summary

Fase 0 ("destravar") do sprint eval-baseline. O disco **local** está cheio; o HD externo (onde mora `ML_CACHE_ROOT`) tem espaço. Hoje os caches de modelos do Docker já vão pro HD externo, mas **downloads de dataset, staging do HF e cache `uv` caem no disco local por padrão** — e o sprint vai baixar HarmBench/AdvBench/FAQ_BACEN, então estoura no meio. A abordagem: (1) um módulo `guardrails/env_bootstrap.py` que carrega `.env` e **deriva** `HF_HOME`/`HF_DATASETS_CACHE`/`HF_HUB_CACHE`/`TRANSFORMERS_CACHE`/`TMPDIR` a partir de `ML_CACHE_ROOT` quando não setados explicitamente, importado **antes** de `datasets`/`transformers`; (2) um `.env.example` commitado documentando todas as vars (inclusive as shell-level que o Python não controla — `UV_CACHE_DIR`, e docker); (3) autoload no `conftest.py` raiz (caminho do `pytest -m adversarial`) e como 1ª linha dos scripts que chamam `load_dataset()`.

Princípio de design: o usuário seta **só** `ML_CACHE_ROOT` (e os segredos) e todo o resto resolve sozinho para um caminho com espaço — satisfazendo AC#3 sem fazer o usuário decorar 6 variáveis.

## User Story

Como autor (técnico)
Quero apontar `HF_HOME`/`HF_DATASETS_CACHE`/`TMPDIR`/cache `uv` pro HD externo
Para que os downloads do sprint não estourem o disco local e eu consiga rodar o eval de fato.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (infra/config) |
| Complexity | LOW |
| Systems Affected | config/bootstrap, pytest harness, scripts de dataset, docs |
| Jira Issue | SCRUM-19 (epic SCRUM-18) |

---

## Decisões de design (fork resolvido)

- **Como o `.env` é lido:** módulo `guardrails/env_bootstrap.py` chamando `dotenv.load_dotenv()` (não-override: ambiente real ganha do arquivo). `python-dotenv` já vem transitivo via `pydantic-settings`, mas será adicionado **explícito** por higiene.
- **Derivação a partir de `ML_CACHE_ROOT`:** o bootstrap, se `ML_CACHE_ROOT` estiver setado e `HF_*` não, faz `HF_HOME=$ML_CACHE_ROOT/huggingface` etc. Idempotente, usa `setdefault`.
- **Split in-process vs shell:** o bootstrap resolve o que o **Python** lê (`HF_*`, `TMPDIR`). `UV_CACHE_DIR` (lido pelo binário `uv`) e o cache de build do Docker **não** podem ser setados por Python → ficam **documentados** no `.env.example` + README para `set -a; source .env; set +a` antes de `uv run`/`docker compose`.
- **Ordem de import é crítica:** HF lê as env vars no `import datasets`/`transformers`. Logo o bootstrap precisa rodar **antes** desses imports → 1ª linha do `conftest.py` e dos scripts.

---

## Patterns to Follow

### Env var já no estilo do projeto (setdefault, sem override)
```python
# SOURCE: conftest.py:12
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
```

### Substituição `${VAR}` no YAML que o config.py já faz (o .env alimenta isso via os.environ)
```python
# SOURCE: guardrails/config.py:9-19
_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")

def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        # se a var não existir, MANTÉM o literal ${VAR} (não há suporte a :-default)
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    ...
```
> Nota: o loader **não** suporta `${VAR:-default}` — só `${VAR}`. Defaults ficam no `.env.example`/compose, não no YAML.

### Caminho-default do HD externo já usado no compose (fonte canônica do exemplo)
```yaml
# SOURCE: docker-compose.yml:27
- ${ML_CACHE_ROOT:-/run/media/germano/Novo volume/Linux/ml-cache}/torch:/root/.cache/torch:rw
```

### Convenção de script (header docstring + `from __future__`)
```python
# SOURCE: scripts/ingest_itau_faq.py:1-10 (topo de script típico)
"""<docstring>"""
from __future__ import annotations
import ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `guardrails/env_bootstrap.py` | CREATE | Carrega `.env` + deriva caches HF de `ML_CACHE_ROOT`; idempotente; sem deps pesadas |
| `.env.example` | CREATE | Documenta todas as vars (cache + segredos + shell-level) com exemplos placeholder |
| `conftest.py` | UPDATE | Importa `env_bootstrap` como 1ª coisa (caminho `pytest -m adversarial`) |
| `scripts/ingest_itau_faq.py` | UPDATE | 1ª linha: import do bootstrap antes de `datasets` |
| `scripts/build_jailbreak_index.py` | UPDATE | idem |
| `scripts/build_outofscope_seeds.py` | UPDATE | idem |
| `scripts/screen_realtoxicityprompts.py` | UPDATE | idem |
| `scripts/finetune_itau_embedding.py` | UPDATE | idem (backlog, mas chama `load_dataset` — patch barato) |
| `pyproject.toml` | UPDATE | Adiciona `python-dotenv>=1.0` às dependencies |
| `README.md` | UPDATE | Seção "Setup de cache (.env)" com `set -a; source .env; set +a` |
| `.gitignore` | VERIFY | `.env` já ignorado (linha 11); confirmar `.env.example` versionado (não precisa mudar) |

---

## Tasks

Executar em ordem. Cada uma é atômica e verificável.

### Task 1: Criar o módulo de bootstrap de ambiente

- **File**: `guardrails/env_bootstrap.py`
- **Action**: CREATE
- **Implement**:
  - Docstring + `from __future__ import annotations`.
  - `import os` e `from pathlib import Path`.
  - `load_dotenv()` via `python-dotenv`, procurando `.env` na raiz do repo (`Path(__file__).resolve().parents[1] / ".env"`); `override=False`. Envolver em `try/except ImportError` com warning silencioso (degrada se dotenv ausente, mas dotenv estará nas deps).
  - Função `_derive_hf_caches()`: se `os.environ.get("ML_CACHE_ROOT")` existir, fazer `os.environ.setdefault` para `HF_HOME`, `HF_DATASETS_CACHE`, `HF_HUB_CACHE`, `TRANSFORMERS_CACHE` (todos sob `$ML_CACHE_ROOT/huggingface`) e `TMPDIR` (`$ML_CACHE_ROOT/tmp`, criando o dir com `mkdir(parents=True, exist_ok=True)`).
  - Manter `os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")` aqui também (centralizar).
  - Rodar tudo **no import do módulo** (top-level), idempotente.
- **Mirror**: `conftest.py:12` (estilo `setdefault`); `guardrails/config.py:5-7` (imports `os`/`Path`).
- **Validate**: `uv run python -c "import guardrails.env_bootstrap"`

### Task 2: Adicionar `python-dotenv` às dependências

- **File**: `pyproject.toml`
- **Action**: UPDATE
- **Implement**: adicionar `"python-dotenv>=1.0",` na lista `dependencies` (já vem transitivo de `pydantic-settings`, mas tornar explícito). Rodar `uv lock` se necessário.
- **Mirror**: `pyproject.toml:5-23` (formato da lista).
- **Validate**: `uv sync && uv run python -c "import dotenv; print(dotenv.__version__)"`

### Task 3: Autoload no conftest raiz (caminho do pytest)

- **File**: `conftest.py`
- **Action**: UPDATE
- **Implement**: depois de inserir o root no `sys.path` (linha 8), adicionar `import guardrails.env_bootstrap  # noqa: F401,E402` para que **antes** de qualquer teste importar `transformers`/`datasets` as env vars já estejam setadas. Remover o `setdefault("TOKENIZERS_PARALLELISM",...)` daqui (migrou pro bootstrap) **ou** deixar (idempotente) — preferir remover pra evitar duplicação.
- **Mirror**: `conftest.py:1-13` (estrutura atual).
- **Validate**: `uv run python -c "import conftest; import os; print(os.environ.get('HF_HOME'))"` (com `ML_CACHE_ROOT` setado deve imprimir o caminho derivado).

### Task 4: Patchar os scripts que chamam `load_dataset()`

- **File**: `scripts/ingest_itau_faq.py`, `scripts/build_jailbreak_index.py`, `scripts/build_outofscope_seeds.py`, `scripts/screen_realtoxicityprompts.py`, `scripts/finetune_itau_embedding.py`
- **Action**: UPDATE
- **Implement**: como **primeira linha executável** (após a docstring e `from __future__`), adicionar:
  ```python
  import guardrails.env_bootstrap  # noqa: F401  # redireciona caches HF p/ ML_CACHE_ROOT — DEVE vir antes de importar datasets/transformers
  ```
  Garantir que vem **antes** de `import datasets` / `from datasets import ...` / `import sentence_transformers` em cada arquivo.
- **Mirror**: `scripts/ingest_itau_faq.py:1-15` (ordem de imports).
- **Validate**: `uv run python -c "import ast,sys; [print(f) for f in sys.argv[1:]]" scripts/*.py` + revisão visual de que o import do bootstrap precede `datasets`.

### Task 5: Criar `.env.example`

- **File**: `.env.example`
- **Action**: CREATE
- **Implement**: arquivo comentado, agrupado, com placeholders (sem segredos reais). Conteúdo:
  - **Cache (núcleo do SCRUM-19):**
    - `ML_CACHE_ROOT="/run/media/germano/Novo volume/Linux/ml-cache"` — raiz no HD externo; tudo abaixo deriva dela.
    - Comentário explicando que `HF_HOME`/`HF_DATASETS_CACHE`/`HF_HUB_CACHE`/`TRANSFORMERS_CACHE`/`TMPDIR` são **derivados automaticamente** pelo `env_bootstrap.py` — só descomente para sobrescrever.
    - `# HF_HOME="${ML_CACHE_ROOT}/huggingface"` (comentado, exemplo de override)
    - `# HF_DATASETS_CACHE="${ML_CACHE_ROOT}/huggingface/datasets"`
    - `# TMPDIR="${ML_CACHE_ROOT}/tmp"`
  - **Shell-level (Python NÃO controla — precisa `source` antes de `uv`/docker):**
    - `UV_CACHE_DIR="${ML_CACHE_ROOT}/uv-cache"`
    - Comentário: "estas valem só se você fizer `set -a; source .env; set +a` antes de `uv run`/`docker compose`".
  - **Segredos (placeholders):**
    - `ANTHROPIC_API_KEY="sk-ant-..."`
    - `HF_TOKEN="hf_..."` (necessário p/ repos gated: Necent, Prompt-Guard-2)
  - **Runtime (já usados no compose):**
    - `QDRANT_HOST="localhost"`, `QDRANT_COLLECTION="banking_kb"` (nota: precedência tratada no SCRUM-20), `LLM_PROVIDER="anthropic"`, `HF_HUB_OFFLINE=0`, `TRANSFORMERS_OFFLINE=0`.
- **Mirror**: nomes/defaults de `docker-compose.yml:18-28` (fonte canônica das vars).
- **Validate**: `set -a; source .env.example; set +a; echo "$ML_CACHE_ROOT"` (parseia sem erro; caminho com espaço entre aspas resolve).

### Task 6: Documentar no README

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: seção curta "Setup de cache / `.env`":
  - `cp .env.example .env` e editar `ML_CACHE_ROOT` + segredos.
  - Para pytest/scripts Python: o `env_bootstrap` carrega o `.env` automaticamente.
  - Para `uv run`/`docker compose`: `set -a; source .env; set +a` antes (porque `UV_CACHE_DIR` e o build do Docker são shell-level).
  - Avisar que `.env` é gitignored e nunca deve ser commitado (só `.env.example`).
- **Mirror**: estrutura de seções existente do `README.md`.
- **Validate**: revisão visual; `grep -q "ML_CACHE_ROOT" README.md`.

### Task 7: Verificar `.gitignore`

- **File**: `.gitignore`
- **Action**: VERIFY (provável no-op)
- **Implement**: confirmar que `.env` (linha 11) ignora o real e que `.env.example` **não** casa com nenhum padrão. Se quiser ser explícito, adicionar `!.env.example` logo após `.env`. Opcional.
- **Mirror**: `.gitignore:10-12`.
- **Validate**: `git check-ignore .env && ! git check-ignore .env.example && echo OK`

---

## Risks

| Risk | Mitigation |
|------|------------|
| Bootstrap roda **depois** de `import datasets`/`transformers` → HF já leu cache default | Import do bootstrap como 1ª linha do conftest e dos scripts; revisar ordem em cada script no Task 4 |
| `UV_CACHE_DIR`/build do Docker não respeitam o bootstrap (são shell/binário) | Documentar `set -a; source .env; set +a` no README + `.env.example`; fora do escopo do bootstrap Python |
| Segredo real vazar via `.env.example` | Só placeholders no exemplo; `.env` permanece gitignored (linha 11) |
| Caminho com espaço ("Novo volume") quebra parsing | Valores entre aspas no `.env.example`; `pathlib.Path` lida nativamente; validar no Task 5 |
| `python-dotenv` ausente em algum ambiente | Adicionado explícito às deps (Task 2) + `try/except ImportError` degradando com warning |
| `datasets` é optional-group → script falha no import | Fora do escopo do SCRUM-19 (é SCRUM-21); apenas anotar. Bootstrap não importa `datasets`. |

---

## Validation

```bash
# 1. Bootstrap importa e deriva os caches a partir de ML_CACHE_ROOT
ML_CACHE_ROOT=/tmp/ml-cache-test uv run python -c "import guardrails.env_bootstrap, os; print('HF_HOME =', os.environ['HF_HOME']); print('HF_DATASETS_CACHE =', os.environ['HF_DATASETS_CACHE']); print('TMPDIR =', os.environ['TMPDIR'])"

# 2. Lint/format
uv run ruff check guardrails/env_bootstrap.py conftest.py scripts/
uv run ruff format --check .

# 3. .env.example parseia e não vaza segredo
set -a; source .env.example; set +a; echo "ML_CACHE_ROOT=$ML_CACHE_ROOT"
grep -iE "sk-ant-[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}" .env.example && echo "VAZOU SEGREDO" || echo "ok, só placeholders"

# 4. gitignore correto
git check-ignore .env >/dev/null && ! git check-ignore .env.example >/dev/null && echo "gitignore OK"

# 5. Smoke do harness (não baixa nada; só coleta)
uv run pytest -m "adversarial" --collect-only -q
```

---

## Acceptance Criteria (mapeado pro Jira)

- [ ] **AC1** — Given disco local cheio, when rodo `load_dataset`/`pytest -m adversarial`, then sem `ENOSPC` (staging/cache vão pro HD externo via bootstrap + `.env`)
- [ ] **AC2** — Given um clone novo, when leio `.env.example`, then todas as variáveis de cache estão documentadas com exemplo
- [ ] **AC3** — Given `ML_CACHE_ROOT` e os caches HF/uv, then todos resolvem para um caminho com espaço (HF derivados pelo bootstrap; `uv`/`TMPDIR` documentados)
- [ ] Lint/format passam
- [ ] `.env` permanece gitignored; só `.env.example` versionado
- [ ] Segue os padrões existentes (`setdefault`, sem override do ambiente real)

---

## Notas para o `/implement`

- Não commitar `.env`. Ao final, propor mensagem `feat(infra): redireciona caches ML/datasets pro HD externo + .env.example (SCRUM-19)` e pedir confirmação (workflow CLAUDE.md: trabalhar direto na `main`, perguntar antes de commitar).
- Validação real de AC1 (ausência de `ENOSPC`) só acontece quando um `load_dataset` pesado roda — citar como verificação manual pós-merge, não bloquear o gate automático.
- Depende de nada; **destrava** SCRUM-22..35.
