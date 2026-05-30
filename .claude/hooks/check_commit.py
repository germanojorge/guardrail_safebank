#!/usr/bin/env python3
"""Hook de Stop: re-engaja o Claude principal pra ponderar se vale commitar.

Em vez de delegar a decisão a um modelo separado, este hook injeta o estado do
git de volta no contexto do próprio Claude (via decision=block) pra que ELE
avalie, com o contexto completo da sessão, se as mudanças formam uma unidade
coesa — e, em caso afirmativo, pergunte ao usuário se quer commitar.

Guarda anti-loop: se já estamos num ciclo disparado por este hook
(`stop_hook_active`), sai em silêncio pra não re-bloquear indefinidamente.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_git_status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
    ).stdout[:3000]  # limita pra não explodir o contexto

    return f"Status (--stat):\n{diff}\n{diff_cached}\n\nDiff (truncado em 3000 chars):\n{diff_content}"


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}

    # Anti-loop: se já fomos re-engajados por este mesmo hook, não bloqueia de novo.
    if hook_input.get("stop_hook_active"):
        sys.exit(0)

    status = get_git_status()
    if not status:
        sys.exit(0)

    diff_info = get_git_diff()

    instruction = (
        "Há mudanças não commitadas no repositório. Antes de encerrar, pondere "
        "se elas formam uma unidade lógica coerente e completa que valha um commit "
        "(uma feature, um fix, uma refatoração — não algo em progresso ou trivial).\n\n"
        "- Se VALER: avise o usuário e pergunte se ele quer commitar agora, propondo "
        "uma mensagem de commit (Conventional Commits, em português). Só commite após "
        "ele confirmar.\n"
        "- Se NÃO valer (mudança incompleta, em progresso ou trivial): diga isso em "
        "uma linha e encerre, sem insistir.\n\n"
        f"Estado atual do git:\n{diff_info}"
    )

    print(json.dumps({"decision": "block", "reason": instruction}))


if __name__ == "__main__":
    main()
