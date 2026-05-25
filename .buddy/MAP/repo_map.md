🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Repo Map

Every file in the repo and what it does.

## Source files (the real code)

| File | Purpose |
|---|---|
| `guardrails.py` | Core of the project. Two classes: `EnhancedLLMGuardrails` (toxicity, PII, intent) and `CustomGuardrails` (prompt injection). Can also be run directly as a script for a quick demo. |
| `real_chatbot.py` | Connects the guardrails to the Claude API. `RealLLMChatbot` class + interactive CLI loop in `main()`. |
| `test_guardrails.py` | Manual test script. No test framework — uses `print` to show pass/fail. |
| `main.py` | Placeholder entry point. Prints "Hello from llm-guardrails-tutorial!". Not connected to the guardrails yet. |

## Config files

| File | Purpose |
|---|---|
| `config.yaml` | Your API key and model name. **Gitignored — you must create this yourself.** |
| `pyproject.toml` | Python project metadata and dependency list (anthropic, detoxify, pyyaml). |
| `uv.lock` | Locked dependency tree. Committed to git. Used by `uv sync`. |
| `.python-version` | Pins the Python version for pyenv/uv. |
| `.gitignore` | Excludes venv, pycache, `config.yaml`, model weights, IDE folders. |

## Folders

| Folder | Purpose |
|---|---|
| `.buddy/` | Buddy's knowledge base — the docs you're reading now. |
| `.claude/` | Claude Code agent config. |
| `.github/` | GitHub Actions or other GitHub config. Contents not scanned. |
| `.git/` | Git internals. Ignore this. |

## Where to start reading code

1. **`guardrails.py`** — Read `EnhancedLLMGuardrails.__init__()` to see what data structures are set up, then `validate_input()` to see the full check pipeline.
2. **`real_chatbot.py`** — Read `RealLLMChatbot.chat()` to see how the guardrails and the Claude API are wired together.
3. **`test_guardrails.py`** — Run it and read the output to understand what each guardrail is expected to catch.
