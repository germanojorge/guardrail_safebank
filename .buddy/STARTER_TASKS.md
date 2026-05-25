🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Starter Tasks

Pick one. Finish it. Move to the next. Small wins build understanding faster than reading.

---

## Warm-up (no code changes needed)

**Run the guardrails and read the output.**
```bash
uv run python guardrails.py
```
Look at each input and ask yourself: did the guardrail make the right call? Can you think of a message that should be blocked but might slip through?

**Run the tests.**
```bash
uv run python test_guardrails.py
```
Do all cases pass? Notice the test for "Como hackear uma senha" (How to hack a password) — trace exactly which check catches it in `guardrails.py`.

---

## First code change (≈ 30–60 min)

**Add a new PII pattern.**
`guardrails.py` currently detects emails, Brazilian phone numbers, CPF, and credit cards. Brazilian postal codes (CEP) look like `12345-678`. Add a regex for them in the `pii_patterns` dict and add a test case in `test_guardrails.py`.

**Make the toxicity threshold configurable.**
Right now, the threshold `0.7` is hardcoded in `verificar_toxicidade()`. Add an `__init__` parameter `toxicity_threshold=0.7` so callers can set it. Update the test file to verify a custom threshold works.

**Add a blocked topic check to `CustomGuardrails`.**
The `CustomGuardrails` class accepts a `blocked_topics` list but never actually uses it to filter messages. Implement that check in a new method `check_blocked_topics(texto: str) -> Dict` and wire it into `RealLLMChatbot.chat()`.

---

## Deeper exploration (≈ 1–2 hrs)

**Try to bypass the intent detector.**
Think of a way to ask for "hacking help" without using any word from `harmful_keywords`. Does the guardrail catch it? Document what you find in `NOTES/open_questions.md`. This is exactly the adversarial review the building-rigorously approach recommends.

**Replace print-based tests with pytest.**
Install pytest (`uv add --dev pytest`) and convert `test_guardrails.py` into proper `assert`-based test cases. This makes failures easier to spot.

**Add a length check.**
Very long messages can be expensive to send to Claude. Add an input length check to `validate_input()` that blocks messages over, say, 2000 characters and add a test for it.

---

## Tips

- The guardrail classes are independent. You can import and test them without an API key.
- If a task takes more than 30 minutes just to understand, that confusion is worth writing down in `NOTES/open_questions.md`.
- Keep changes small. One function at a time.
