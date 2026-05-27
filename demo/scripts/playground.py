"""Playground interativo — testa /chat (input+output) ou /debug/output-guard.

Uso:
    uv run python demo/scripts/playground.py
    python demo/scripts/playground.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"

# ── cores ANSI ──────────────────────────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _print_result(result: dict, mode: str) -> None:
    blocked = result.get("blocked", False)
    status = f"{RED}{BOLD}BLOQUEADO{RESET}" if blocked else f"{GREEN}{BOLD}PASSOU{RESET}"

    print(f"\n{BOLD}{'─' * 50}{RESET}")
    print(f"  Status : {status}")

    if blocked:
        category = result.get("category") or result.get("block_category") or "—"
        rule = result.get("rule_violated") or "—"
        reasoning = result.get("reasoning")
        print(f"  Guardrail : {YELLOW}{category}{RESET}")
        print(f"  Regra     : {YELLOW}{rule}{RESET}")
        if reasoning:
            print(f"  Reasoning : {reasoning}")
    else:
        if mode == "input":
            response = result.get("response", "")
            if response:
                print(f"  Resposta  : {response[:200]}{'…' if len(response) > 200 else ''}")

    # latência
    if mode == "input":
        lat = result.get("diagnostics", {}).get("latency_ms", {})
        if isinstance(lat, dict):
            parts = [f"{k}={v:.0f}ms" for k, v in lat.items() if v is not None and k != "total"]
            total = lat.get("total")
            if parts:
                print(f"  Latência  : {', '.join(parts)}" + (f" | total={total:.0f}ms" if total else ""))
    else:
        lat = result.get("latency_ms")
        if lat is not None:
            print(f"  Latência  : {lat:.0f}ms")

    print(f"{BOLD}{'─' * 50}{RESET}")
    print(f"\n{CYAN}JSON completo:{RESET}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _choose_mode() -> str:
    print(f"\n{BOLD}Modo:{RESET}")
    print(f"  {BOLD}1{RESET} — /chat          (pipeline completo: input guard → RAG → LLM → output guard)")
    print(f"  {BOLD}2{RESET} — /debug/output-guard  (só output guard — injeta resposta diretamente)")
    while True:
        choice = input("\nEscolha [1/2]: ").strip()
        if choice in ("1", "2"):
            return "input" if choice == "1" else "output"
        print("  Digite 1 ou 2.")


def main() -> None:
    print(f"\n{BOLD}🛡  Guardrail Playground{RESET}")
    print("Ctrl+C para sair  |  Enter em branco para trocar de modo\n")

    # verifica se a API tá no ar
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=3)
    except Exception:
        print(f"{RED}API não encontrada em {BASE_URL} — rode 'docker compose up' primeiro.{RESET}")
        sys.exit(1)

    mode = _choose_mode()

    while True:
        label = "Mensagem (usuário)" if mode == "input" else "Resposta do LLM (texto a validar)"
        try:
            text = input(f"\n{BOLD}{label}:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nTchau!")
            break

        if not text:
            mode = _choose_mode()
            continue

        path = "/chat" if mode == "input" else "/debug/output-guard"
        field = "message" if mode == "input" else "response"

        print(f"\n{CYAN}→ POST {path}{RESET}")
        try:
            result = _post(path, {field: text})
            _print_result(result, mode)
        except urllib.error.URLError as exc:
            print(f"{RED}Erro de conexão: {exc}{RESET}")
        except Exception as exc:
            print(f"{RED}Erro inesperado: {exc}{RESET}")


if __name__ == "__main__":
    main()
