"""Bootstrap de ambiente para o guardrail-safebank.

Carrega `.env` da raiz do repositório (sem override de variáveis já setadas)
e deriva caches HF/Temp a partir de `ML_CACHE_ROOT` quando as variáveis
específicas não estão explicitamente configuradas.

Importar este módulo como **primeira coisa** em qualquer script ou harness
que venha a importar `datasets` / `transformers` / `sentence_transformers`,
pois o Hugging Face lê as env vars de cache no momento do import.

Uso típico (conftest.py, scripts de dataset):
    import guardrails.env_bootstrap  # noqa: F401
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path


def _load_dotenv() -> None:
    """Tenta carregar `.env` da raiz do repo via python-dotenv (override=False)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        warnings.warn(
            "python-dotenv não está instalado — variáveis de .env não serão carregadas automaticamente. Instale com: uv add python-dotenv",
            stacklevel=2,
        )
        return

    # Raiz do repo = dois níveis acima de guardrails/env_bootstrap.py
    repo_root = Path(__file__).resolve().parents[1]
    dotenv_path = repo_root / ".env"
    if not dotenv_path.exists():
        return

    try:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"Falha ao parsear {dotenv_path}: {exc}. Variáveis de .env serão ignoradas.",
            stacklevel=2,
        )


def _derive_hf_caches() -> None:
    """Deriva caches HF a partir de ML_CACHE_ROOT, usando setdefault (idempotente)."""
    ml_cache_root = os.environ.get("ML_CACHE_ROOT")
    if not ml_cache_root:
        return

    root = Path(ml_cache_root)
    hf_base = root / "huggingface"
    tmp_dir = root / "tmp"

    # Cria diretórios se possível; não quebra se não tiver permissão
    # (o HF/uv criam sob demanda depois)
    for d in (hf_base, tmp_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    os.environ.setdefault("HF_HOME", str(hf_base))
    os.environ.setdefault("HF_DATASETS_CACHE", str(hf_base / "datasets"))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_base / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_base / "transformers"))
    os.environ.setdefault("TMPDIR", str(tmp_dir))


# ── Executa no import do módulo (idempotente) ──
_load_dotenv()
_derive_hf_caches()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
