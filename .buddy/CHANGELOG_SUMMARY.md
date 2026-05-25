🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Recent Changes (Human-Friendly)

Summarized from `git log`. Last indexed commit: `9204c2a`.

---

## 2025-11-03 — Add .gitignore and stop tracking venv (`9204c2a`)

- Added a `.gitignore` file covering `venv/`, `__pycache__`, `.env`, `.env.*`, `config.yaml`, model files (`.pt`, `.bin`, `.onnx`), and common IDE folders.
- Stopped tracking the `venv/` folder in git (it was accidentally committed in the first commit).
- This means the API key in `config.yaml` is now gitignored — which is the right thing, since `config.yaml` holds a real key.

## 2025-11-03 — First commit (`463b9fb`)

- Initial project: `guardrails.py`, `real_chatbot.py`, `test_guardrails.py`, `main.py`, `pyproject.toml`, `uv.lock`, `config.yaml`.
- Set up the `EnhancedLLMGuardrails` class with toxicity detection, PII masking, and intent checking.
- Set up the `CustomGuardrails` class with prompt injection detection.
- Set up `RealLLMChatbot` wiring all guardrails to the Claude API.

---

*This file is updated by Buddy. Run "update buddy" before committing to keep it current.*
