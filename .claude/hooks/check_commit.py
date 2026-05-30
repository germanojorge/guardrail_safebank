#!/usr/bin/env python3
"""Hook de Stop: re-engaja o Claude principal pra perguntar se vale commitar.

Quando há mudanças não commitadas, bloqueia o stop e injeta um lembrete curto
(via decision=block) pra que o Claude pergunte ao usuário se ele quer commitar.
NÃO injeta o diff — só a lista de arquivos alterados, pra mensagem ficar enxuta.
Se o Claude precisar inspecionar o conteúdo, roda `git diff` por conta própria.

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

    instruction = (
        "Há mudanças não commitadas. Pergunte ao usuário, de forma curta, se ele "
        "quer commitar agora — propondo uma mensagem de commit (Conventional Commits, "
        "em português). NÃO mostre o diff. Só commite após ele confirmar. Se as "
        "mudanças parecerem incompletas/triviais, diga isso em uma linha e encerre.\n\n"
        f"Arquivos alterados:\n{status}"
    )

    print(json.dumps({"decision": "block", "reason": instruction}))


if __name__ == "__main__":
    main()
