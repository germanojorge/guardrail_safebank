#!/usr/bin/env python3
"""Hook de UserPromptSubmit: garante que o trabalho aconteça na branch `main`.

Decisão do usuário (2026-05-30): por enquanto trabalhamos sempre direto na
`main` (projeto solo, objetivo de manter o heatmap aceso — commits só contam
no GitHub quando estão na default branch).

A cada prompt, checa a branch atual. Se NÃO for `main`, avisa o usuário
(systemMessage) e injeta um lembrete no contexto do Claude (additionalContext)
pra que ele ofereça voltar pra `main`. Não troca de branch sozinho — mover o
working tree à revelia poderia carregar mudanças não-commitadas pra outro lugar.
Se já estamos na `main`, sai em silêncio.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
TARGET_BRANCH = "main"


def current_branch() -> str:
    return subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main():
    branch = current_branch()

    # Vazio = detached HEAD ou fora de repo git; não atrapalha.
    if not branch or branch == TARGET_BRANCH:
        sys.exit(0)

    aviso = (
        f"⚠️ Você está na branch '{branch}', mas a preferência é trabalhar sempre "
        f"na '{TARGET_BRANCH}' por enquanto."
    )
    contexto = (
        f"ATENÇÃO: a branch atual é '{branch}', não '{TARGET_BRANCH}'. O usuário "
        f"definiu que o trabalho deve acontecer direto na '{TARGET_BRANCH}'. Antes de "
        f"editar código, ofereça voltar pra '{TARGET_BRANCH}' (git checkout {TARGET_BRANCH}), "
        f"tomando cuidado com mudanças não-commitadas no working tree (avise se houver). "
        f"Não troque de branch sem confirmar com o usuário."
    )

    print(
        json.dumps(
            {
                "systemMessage": aviso,
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": contexto,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
