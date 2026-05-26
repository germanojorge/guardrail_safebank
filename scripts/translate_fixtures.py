#!/usr/bin/env python
"""
One-shot script to translate JailbreakBench EN prompts to PT-BR.

Reads DEBERTA_ONLY_SAMPLES from tests/fixtures/jailbreak_samples.py, calls
Claude (via AnthropicProvider.complete()) with a translation prompt that
preserves adversarial intent, and writes the results to a JSONL file.

Idempotent: skips output if it already exists (use --force to re-run).

Usage:
    ANTHROPIC_API_KEY=... uv run python scripts/translate_fixtures.py

Output:
    tests/adversarial/fixtures/jailbreak_translated.jsonl
    (merge with EN source in jailbreak_external.jsonl by Task 6)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUTPUT = Path("tests/adversarial/fixtures/jailbreak_translated.jsonl")

# Import EN source samples
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.fixtures.jailbreak_samples import DEBERTA_ONLY_SAMPLES  # noqa: E402

TRANSLATION_PROMPT = (
    "You are a precise PT-BR translator. Translate the following English jailbreak prompt "
    "to Brazilian Portuguese. Preserve the exact adversarial intent, tone, and structure. "
    "Return ONLY the translated text, no explanations, no quotes, no labels. "
    "If the prompt contains a scenario (e.g. researcher persona, fiction framing), "
    "preserve the scenario framing in Portuguese."
)


def _load_anthropic_provider():
    from guardrails.adapters.llm import AnthropicProvider

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY env var required", file=sys.stderr)
        raise SystemExit(1)
    return AnthropicProvider()


def _translate(provider, text: str) -> str:
    result = provider.complete(
        messages=[{"role": "user", "content": f"{TRANSLATION_PROMPT}\n\n{text}"}],
        temperature=0.3,
        max_tokens=512,
    )
    return result.strip()


def _write_output(entries: list[dict]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(
            "# Source: JailbreakBench v1.0 (https://github.com/JailbreakBench/jailbreakbench)\n"
        )
        f.write("# License: MIT\n")
        f.write("# Access date: 2026-05-26\n")
        f.write(
            "# Translation: Claude via AnthropicProvider, PT-BR, "
            "preserving adversarial intent\n"
        )
        f.write(
            "# Manual review checklist: verify each line preserves the original "
            "jailbreak semantics\n"
        )
        f.write(
            "#   and does not soften the adversarial request. Flag any line where "
            "the translation\n"
        )
        f.write("#   reduces urgency, specificity, or adversarial framing.\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[translate] wrote {len(entries)} lines to {OUTPUT}")


def main() -> int:
    if OUTPUT.exists():
        print(f"[translate] output exists: {OUTPUT}")
        if "--force" not in sys.argv:
            print("[translate] use --force to overwrite")
            return 0
        print("[translate] --force: overwriting")

    provider = _load_anthropic_provider()
    entries: list[dict] = []
    for sample_id, text in DEBERTA_ONLY_SAMPLES:
        translated = _translate(provider, text)
        entries.append(
            {
                "id": f"{sample_id}_ptbr",
                "text": translated,
                "lang": "pt-br",
                "source": "jailbreakbench-translated",
                "technique": "translated",
                "expected": "block",
            }
        )
        print(f"  [{sample_id}] → {translated[:80]!r}")

    _write_output(entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
