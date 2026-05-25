🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Entry Points

Where execution starts when you run the project.

| Entry point | How to run | What it does |
|---|---|---|
| `real_chatbot.py` — `main()` | `uv run python real_chatbot.py` | Interactive CLI chatbot. The main user-facing entry point. Loads config, starts the guardrails, opens a read-eval-print loop. |
| `guardrails.py` — `__main__` block | `uv run python guardrails.py` | Demo script. Runs a fixed list of test inputs through `EnhancedLLMGuardrails.validate_input()` and prints results. No API key needed. |
| `test_guardrails.py` — `__main__` block | `uv run python test_guardrails.py` | Runs `test_funcionalidade_basica()` and `test_injecao_de_prompt()`. No API key needed. |
| `main.py` — `main()` | `uv run python main.py` | Placeholder. Just prints "Hello from llm-guardrails-tutorial!". Not connected to guardrails. |

## There is no web server

This project has no HTTP server. It is entirely command-line and in-process. There are no ports, no routes, no REST endpoints.
