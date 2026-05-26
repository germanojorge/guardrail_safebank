"""Config loader for the guardrail pipeline."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def load_config(path: str | None = None) -> dict[str, Any]:
    import yaml

    config_path = path or "config.yaml"
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    return _expand_env_vars(raw)


_config_cache: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    global _config_cache
    if _config_cache is None:
        _config_cache = load_config()
    return _config_cache
