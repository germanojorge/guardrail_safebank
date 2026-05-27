"""Root conftest — project-wide pytest configuration.

Sets sys.pycache_prefix so all bytecode generated during test runs lands in
.cache/pycache/ instead of scattering __pycache__/ directories across the tree.
For non-pytest runs (uv run, plain python) set PYTHONPYCACHEPREFIX=.cache/pycache
in your shell or .env file.
"""

import sys
from pathlib import Path

sys.pycache_prefix = str(Path(__file__).parent / ".cache" / "pycache")
