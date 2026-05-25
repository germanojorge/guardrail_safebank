🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Open Questions

Things Buddy could not answer from the code alone.

---

## What is in `.github/`?

The `.github/` directory exists but its contents were not scanned. It may contain GitHub Actions workflows. Check `.github/workflows/` to find out if there is CI.

**Where to look:** `ls .github/`

---

## Is `main.py` intentionally a placeholder?

`main.py` only prints "Hello from llm-guardrails-tutorial!" and is declared as the project entry point in `pyproject.toml`. It seems like it was meant to be wired up to the chatbot or guardrails eventually. Is this intentional scaffolding for students to fill in?

**Where to look:** `main.py`, `pyproject.toml`

---

## What is the intended teaching structure?

The project has both `guardrails.py` (which can run standalone) and `real_chatbot.py` (which needs an API key). Is the intended learning path:
1. Run `guardrails.py` first to understand the concepts
2. Then run `real_chatbot.py` with a key to see it integrated?

This is inferred from the structure but not documented anywhere.

---

## Does the `blocked_topics` parameter in `CustomGuardrails` actually do anything?

`CustomGuardrails.__init__()` stores `blocked_topics` as `self.blocked_topics` but no method uses that attribute. The topic blocking feature appears to be unimplemented. Confirm by searching for `self.blocked_topics` in `guardrails.py`.

---

## API key security

`config.yaml` contains a real Anthropic API key in the git history (commit `463b9fb`). Even though `config.yaml` is now gitignored, the key was committed once and may still be in the git history. The key should be rotated if this repo is ever shared publicly.

**Note:** Buddy does not store or reproduce API keys. This note is only to flag that the situation exists.
