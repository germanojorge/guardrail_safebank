🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Important Links

External docs that are useful for understanding or extending this project.

Add a link: `buddy link https://example.com/doc --title "..." --tags setup,api`

Note: Buddy never reads linked pages — it only stores the URL and your description. Paste the content into chat if you want a summary.

---

## Must-read

- **Anthropic API docs** — https://docs.anthropic.com/en/api/getting-started — How to use the Claude API, manage API keys, understand models and pricing. Essential if you change anything in `real_chatbot.py`.
  - Why it matters: `RealLLMChatbot` uses `anthropic.Anthropic.messages.create()`. The docs explain parameters, error codes, rate limits.

- **Detoxify on GitHub** — https://github.com/unitaryai/detoxify — The toxicity detection library used in `EnhancedLLMGuardrails`. Explains the available models (`original`, `unbiased`, `multilingual`) and the score categories.
  - Why it matters: The code uses `Detoxify('original')`. Understanding the model helps you tune the threshold or switch models.

---

## Helpful

- **uv documentation** — https://docs.astral.sh/uv/ — The package manager used in this project. Covers `uv sync`, `uv add`, `uv run`.
  - Why it matters: If you're used to `pip` and `venv`, uv works differently. Read the "Getting started" section.

---

## Optional

*(none yet — add links with `buddy link <url>`)*
