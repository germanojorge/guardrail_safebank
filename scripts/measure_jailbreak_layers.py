#!/usr/bin/env python
"""
Measure substring-only vs substring+DeBERTa block rates on the jailbreak
external fixture dataset.

Loads `tests/adversarial/fixtures/jailbreak_external.jsonl` and runs each
sample through (a) substring-only (use_deberta=False) and (b) full pipeline
(use_deberta=True). Outputs a markdown table that is injected between
`<!-- BEGIN: jailbreak-layer-metrics -->` and `<!-- END: jailbreak-layer-metrics -->`
markers in LIMITATIONS.md.

Usage:
    uv run python scripts/measure_jailbreak_layers.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from guardrails.validators.jailbreak import JailbreakValidator

FIXTURE_PATH = Path("tests/adversarial/fixtures/jailbreak_external.jsonl")
LIMITATIONS_PATH = Path("LIMITATIONS.md")
BEGIN_MARKER = "<!-- BEGIN: jailbreak-layer-metrics -->"
END_MARKER = "<!-- END: jailbreak-layer-metrics -->"


def load_fixtures(path: Path) -> list[dict[str, Any]]:
    """Load JSONL fixtures, skipping comment lines."""
    entries: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            entries.append(json.loads(stripped))
    return entries


def measure(
    validator: JailbreakValidator, entries: list[dict]
) -> dict[str, dict[str, int]]:
    """Run each sample and tally block/pass per language group.

    Returns::
        {
            "en": {"total": N, "blocked": M},
            "pt-br": {"total": N, "blocked": M},
        }
    """
    counts: dict[str, dict[str, int]] = {
        "en": {"total": 0, "blocked": 0},
        "pt-br": {"total": 0, "blocked": 0},
    }
    for entry in entries:
        lang = entry.get("lang", "en")
        if lang not in counts:
            counts[lang] = {"total": 0, "blocked": 0}
        counts[lang]["total"] += 1
        result = validator.run(entry["text"])
        if not result.passed:
            counts[lang]["blocked"] += 1
    return counts


def render_table(sub_only: dict, full: dict) -> str:
    """Render the markdown comparison table."""
    lines = [
        "| Layer | EN block rate | PT-BR block rate | Overall |",
        "|-------|---------------|------------------|---------|",
    ]
    for label, data in [("Substring only", sub_only), ("Substring + DeBERTa", full)]:
        en_total = data["en"]["total"]
        en_blocked = data["en"]["blocked"]
        pt_total = data["pt-br"]["total"]
        pt_blocked = data["pt-br"]["blocked"]
        overall_total = en_total + pt_total
        overall_blocked = en_blocked + pt_blocked

        en_rate = (
            f"{en_blocked}/{en_total} ({en_blocked / en_total:.0%})"
            if en_total
            else "N/A"
        )
        pt_rate = (
            f"{pt_blocked}/{pt_total} ({pt_blocked / pt_total:.0%})"
            if pt_total
            else "N/A"
        )
        overall_rate = (
            f"{overall_blocked}/{overall_total} ({overall_blocked / overall_total:.0%})"
            if overall_total
            else "N/A"
        )

        lines.append(f"| {label} | {en_rate} | {pt_rate} | {overall_rate} |")
    return "\n".join(lines) + "\n"


def update_limitations_md(table: str) -> None:
    """Replace content between BEGIN/END markers in LIMITATIONS.md."""
    content = LIMITATIONS_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(BEGIN_MARKER)}\s*\n).*?(\n{re.escape(END_MARKER)})",
        re.DOTALL,
    )
    replacement = rf"\1{table}\2"
    if not pattern.search(content):
        print(f"[measure] WARNING: markers not found in {LIMITATIONS_PATH}")
        print(f"[measure] Add these markers:\n{BEGIN_MARKER}\n{table}{END_MARKER}")
        return
    content = pattern.sub(replacement, content)
    LIMITATIONS_PATH.write_text(content, encoding="utf-8")
    print(f"[measure] Updated {LIMITATIONS_PATH}")


def main() -> int:
    entries = load_fixtures(FIXTURE_PATH)
    print(f"[measure] loaded {len(entries)} fixtures from {FIXTURE_PATH}")

    en_count = sum(1 for e in entries if e.get("lang") == "en")
    pt_count = sum(1 for e in entries if e.get("lang") == "pt-br")
    print(f"[measure] EN: {en_count}, PT-BR: {pt_count}")

    print("[measure] Measuring substring-only (use_deberta=False) ...")
    sub_only_validator = JailbreakValidator(use_deberta=False)
    sub_only = measure(sub_only_validator, entries)

    print("[measure] Measuring substring+DeBERTa (use_deberta=True) ...")
    full_validator = JailbreakValidator(use_deberta=True)
    full = measure(full_validator, entries)

    table = render_table(sub_only, full)
    print(f"\n[measure] Results:\n{table}")
    update_limitations_md(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
