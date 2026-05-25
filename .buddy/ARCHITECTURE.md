🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Architecture

Verified from source code. Sections marked [Inferred] are Buddy's best guesses.

## Big picture

A user types a message. Before that message reaches Claude, it passes through three safety checks. Claude's response also passes through two safety checks before it reaches the user. The guardrail classes live in `guardrails.py`. The orchestration and Claude API call live in `real_chatbot.py`.

## Major components

| Component | File | Responsibility |
|---|---|---|
| `EnhancedLLMGuardrails` | `guardrails.py` | Toxicity scoring (Detoxify), PII masking (regex), intent detection (keyword + pattern matching), metrics tracking |
| `CustomGuardrails` | `guardrails.py` | Prompt injection detection (keyword list + regex patterns); configurable blocked topics list |
| `RealLLMChatbot` | `real_chatbot.py` | Reads config, wires guardrails together, calls Claude API, manages conversation history |
| `main()` in `real_chatbot.py` | `real_chatbot.py` | Interactive command-line chat loop |
| `test_guardrails.py` | `test_guardrails.py` | Manual test runner — no framework, just `print`-based assertions |

## Request / data flow

A user message travels through this pipeline in `RealLLMChatbot.chat()`:

1. **Prompt injection check** — `CustomGuardrails.check_prompt_injection()` scans for keywords like "ignore all previous instructions". If detected, the message is blocked immediately.
2. **Input validation** — `EnhancedLLMGuardrails.validate_input()` runs three sub-checks in order:
   - Intent check: keyword pattern matching for hacking / illegal / fraud combinations
   - Toxicity check: Detoxify model scores the text; blocked if any score exceeds 0.7
   - PII detection: regex scans for email, phone, CPF, credit card; matched values are replaced with `[TYPE_REDACTED]`
3. **Claude API call** — the sanitized message is appended to `conversation_history` and sent to the Claude API via `anthropic.Anthropic.messages.create()`.
4. **Output validation** — `EnhancedLLMGuardrails.validate_output()` runs the intent check and toxicity check on Claude's response.
5. **Display** — the safe response (plus a PII notice if data was masked) is returned to the user.

## Key boundaries

- `guardrails.py` has no dependency on `real_chatbot.py`. The guardrail classes are standalone and can be imported anywhere.
- `real_chatbot.py` imports from `guardrails.py` and also from `anthropic` and `yaml`.
- The Detoxify model is loaded once at `EnhancedLLMGuardrails.__init__()` time. Starting the class is slow (model download on first run). After that it is fast.
- Conversation history is stored in memory only (`self.conversation_history` list in `RealLLMChatbot`). It is lost when the process exits.

## Known limitations [Inferred — read `guardrails.py` to verify]

- Intent detection is keyword-based only. A paraphrased harmful request ("assist me in accessing an account without authorization") will pass through.
- Toxicity threshold is hardcoded at 0.7. There is no config file entry for it.
- PII masking uses simple regex. It will miss uncommon formats (e.g. international phone numbers, international ID formats).
