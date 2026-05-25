#!/usr/bin/env python3
"""Hook de Stop: pede ao Claude pra avaliar se é boa hora de commitar."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_git_diff() -> str:
    diff = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    ).stdout

    diff_cached = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    ).stdout

    diff_content = subprocess.run(
        ["git", "diff", "--unified=3"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    ).stdout[:3000]  # limita pra não explodir o prompt

    return f"Status:\n{diff}\n{diff_cached}\n\nDiff:\n{diff_content}"


def load_api_key() -> str:
    try:
        import yaml

        config_path = PROJECT_ROOT / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config.get("anthropic_api_key", "")
    except Exception:
        import os

        return os.getenv("ANTHROPIC_API_KEY", "")


def ask_claude(diff_info: str, api_key: str) -> bool:
    """Retorna True se Claude achar que vale a pena commitar agora."""
    import urllib.request

    prompt = f"""Você é um assistente de controle de versão. Analise as mudanças abaixo e diga se é uma boa hora para fazer um commit.

Critérios para SIM:
- As mudanças formam uma unidade lógica coerente (ex: uma feature, um fix, uma refatoração)
- Não parece que o código está no meio de uma mudança incompleta
- Há substância suficiente (não é só renomear uma variável ou ajuste trivial)

Critérios para NÃO:
- Parecem mudanças incompletas ou em progresso
- O diff é muito pequeno ou trivial
- As mudanças parecem não relacionadas entre si

Mudanças no repositório:
{diff_info}

Responda APENAS com JSON: {{"commit": true}} ou {{"commit": false, "reason": "motivo breve"}}"""

    payload = json.dumps(
        {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            # remove markdown code fences se presentes
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            return result.get("commit", False), result.get("reason", "")
    except Exception:
        return False, ""


def main():
    status = get_git_status()
    if not status:
        sys.exit(0)

    api_key = load_api_key()
    if not api_key:
        sys.exit(0)

    diff_info = get_git_diff()
    should_commit, reason = ask_claude(diff_info, api_key)

    if should_commit:
        print(
            json.dumps(
                {
                    "systemMessage": "📝 Bom momento para commitar! As mudanças parecem coesas e completas. Quer fazer o commit agora?"
                }
            )
        )
    # se não, fica em silêncio


if __name__ == "__main__":
    main()
