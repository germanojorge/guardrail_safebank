# LLM Guardrails Tutorial — Home

> **⚠️ OUTDATED — This directory reflects the old PoC architecture.**
> The project has since pivoted: `guardrails_legacy.py` → custom validators in `guardrails/validators/`,
> LangGraph StateGraph orchestration, FastAPI proxy, Docker compose, and structlog JSON logs.
> See [CLAUDE.md](../CLAUDE.md) for the current state, decisions, and architecture.

> This is your home page. Everything links from here.

---

## What is this project?

This is a **tutorial project** that shows how to add safety guardrails around an AI chatbot.

Imagine you build a chatbot. Someone might try to abuse it — swearing at it, asking it to help with hacking, or tricking it into ignoring its own rules. **Guardrails** are the code that catches those attempts and stops them.

This project shows three kinds of protection running on every message:

1. **Toxicity detection** — uses the Detoxify ML model to catch mean, abusive, or hateful language.
2. **PII masking** — finds personal info (emails, phone numbers, Brazilian CPF numbers, credit card numbers) and replaces them with `[REDACTED]` before they reach the AI.
3. **Intent and injection checking** — spots suspicious patterns like "help me hack a password" or "ignore all previous instructions".

When a message passes all checks, it goes to **Claude** (Anthropic's AI) via the Anthropic SDK. The response is checked again before it reaches the user.

---

## Who is this for?

Students and developers learning how to build **safer AI-powered apps**. The code comments and variable names are in Portuguese (Brazilian) but the concepts apply everywhere.

---

## Key concepts in simple words

| Word | What it means |
|---|---|
| Guardrail | A safety check that runs before or after the AI responds |
| PII | Personal Identifiable Information — your email, phone, etc. |
| Toxicity | Abusive or hateful language |
| Prompt injection | Hiding instructions like "forget your rules" inside a normal-looking message to trick an AI |
| Sanitization | Cleaning a message before it goes to the AI (masking PII, etc.) |
| Threshold | The score above which something is considered toxic (default: 0.7 out of 1.0) |

---

## The three main source files

| File | What it does |
|---|---|
| `guardrails.py` | The two guardrail classes. Start reading here. |
| `real_chatbot.py` | Puts the guardrails together with a real Claude API call and a command-line chat loop |
| `test_guardrails.py` | Manual test cases you can run to see the guardrails in action |

---

## Quick links

- [Getting Started](GETTING_STARTED.md) — run it on your machine
- [Architecture](ARCHITECTURE.md) — how the pieces connect
- [Tech Stack](TECH_STACK.md) — what tools are used
- [Integrations](INTEGRATIONS.md) — external services
- [Repo Map](MAP/repo_map.md) — what every file does
- [Data Flow](MAP/data_flow.md) — message path from user to AI and back
- [Starter Tasks](STARTER_TASKS.md) — good first things to try
- [Open Questions](NOTES/open_questions.md) — things not fully clear yet
- [Assumptions](NOTES/assumptions.md) — Buddy's guesses (verify before trusting)
