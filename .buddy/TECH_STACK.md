🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Tech Stack

All evidence comes from `pyproject.toml`, `uv.lock`, and the source files.

## Language

- **Python 3.12+** — the only language in the project

## Key dependencies

| Library | Version (minimum) | What it does |
|---|---|---|
| `anthropic` | >=0.104.1 | Anthropic SDK — sends messages to Claude |
| `detoxify` | >=0.5.2 | ML model that scores text for toxicity |
| `pyyaml` | >=6.0.3 | Reads `config.yaml` |

## Package manager and build tool

- **uv** — modern Python package manager. Lock file is `uv.lock`. Project metadata is in `pyproject.toml`.
- There is no `requirements.txt` — use `uv sync` instead.

## Python version management

- `.python-version` file is present, which means `pyenv` or `uv` can use it to pin the interpreter version.

## Tests

- **No test framework (pytest/unittest) is used.** Tests are plain Python scripts with `print` statements (`test_guardrails.py`). Run with `uv run python test_guardrails.py`.

## CI / Deploy

- A `.github/` directory exists but its contents were not scanned. Check `.github/workflows/` for CI configuration.
- There is no Dockerfile or deployment config visible in the repo root.

## Notable absence

- No linter or formatter config (no `ruff.toml`, `.flake8`, `pyproject.toml` lint section, etc.) was found.
- No type checking config (`mypy.ini`, `pyrightconfig.json`) was found.
