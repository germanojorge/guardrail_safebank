🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# External Integrations

All evidence from `real_chatbot.py` and `pyproject.toml`.

## Services

| Service | What it is used for | Where configured |
|---|---|---|
| Anthropic Claude API | Generates chat responses | `config.yaml` (key: `anthropic_api_key`), or `ANTHROPIC_API_KEY` env var |
| Detoxify (HuggingFace model) | ML toxicity scoring | No config — loaded by name `'original'` in `EnhancedLLMGuardrails.__init__()`. Model weights are downloaded automatically on first run and cached by PyTorch/HuggingFace. |

## No database, no queue, no auth service

This project has no persistent storage, message queue, or authentication layer. Everything runs in a single Python process.

## Secrets and env vars

| Secret | Where it lives | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `config.yaml` (gitignored) or environment variable | `config.yaml` is checked first; env var is the fallback. Never commit a real key. |

**Warning:** `config.yaml` is listed in `.gitignore`. If you clone the repo, this file will not exist and you must create it yourself. See [Getting Started](GETTING_STARTED.md).

## Model config

The Claude model name is set in `config.yaml` under the key `model`. Default value: `claude-sonnet-4-6`. You can change it to any Anthropic model name your key has access to.
