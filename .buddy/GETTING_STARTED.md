🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Getting Started

Everything you need to run this project on your machine.

## Prerequisites

- Python 3.12 or newer (required by `pyproject.toml`)
- [uv](https://github.com/astral-sh/uv) — the package manager used here (replaces pip/venv)
- An Anthropic API key (needed only for `real_chatbot.py`; `test_guardrails.py` works without one)

Check your Python version:
```bash
python --version
```

Install uv if you don't have it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Install

Clone and install dependencies with uv:
```bash
git clone <repo-url>
cd LLM-Guardrails-Tutorial
uv sync
```

`uv sync` reads `pyproject.toml` and `uv.lock` and installs everything into a local virtual environment automatically.

## Configure your API key

`real_chatbot.py` reads the API key from `config.yaml`. That file is gitignored, so you must create it yourself:

```bash
cp config.yaml.example config.yaml   # if an example exists, otherwise create from scratch
```

Edit `config.yaml` to look like this:
```yaml
anthropic_api_key: "sk-ant-..."
model: "claude-sonnet-4-6"
```

You can also set the key as an environment variable instead:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

The chatbot checks `config.yaml` first, then falls back to the environment variable.

**Warning:** Never commit `config.yaml` with a real key. It is already in `.gitignore`.

## Run the guardrails (no API key needed)

This runs the guardrails directly with some built-in test inputs:
```bash
uv run python guardrails.py
```

## Run the test suite (no API key needed)

```bash
uv run python test_guardrails.py
```

You will see each test case print PASSED or FAILED with the input, expected result, and actual result.

## Run the interactive chatbot (API key required)

```bash
uv run python real_chatbot.py
```

Type your messages at the prompt. Special commands:
- `stats` — show guardrail metrics
- `reset` — clear conversation history
- `sair` — quit

## Common problems

**"ModuleNotFoundError: No module named 'detoxify'"**
Run `uv sync` to install dependencies. If uv is not on your PATH, restart your terminal after installing it.

**"AuthenticationError: invalid api key"**
Check that `config.yaml` exists and contains a valid key. See the Configure section above.

**Detoxify download is slow on first run**
The Detoxify model downloads a weights file the first time it runs. This can take a minute on a slow connection. Subsequent runs are fast.

## Where things live

- **Config:** `config.yaml` (gitignored — create it yourself)
- **Dependencies:** `pyproject.toml` and `uv.lock`
- **Logs:** none — output goes to stdout
- **API key:** `config.yaml` or `ANTHROPIC_API_KEY` environment variable
