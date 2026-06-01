"""Root conftest — project-wide pytest configuration.

Sets sys.pycache_prefix so all bytecode generated during test runs lands in
.cache/pycache/ instead of scattering __pycache__/ directories across the tree.
For non-pytest runs (uv run, plain python) set PYTHONPYCACHEPREFIX=.cache/pycache
in your shell or .env file.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o root do projeto está no path para o env_bootstrap
sys.path.insert(0, str(Path(__file__).parent))

# Carrega .env e deriva caches HF *antes* de qualquer teste importar datasets/transformers
import guardrails.env_bootstrap  # noqa: F401,E402

sys.pycache_prefix = str(Path(__file__).parent / ".cache" / "pycache")
