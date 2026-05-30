#!/usr/bin/env python3
"""CLI estilo chatbot pro guardrail-safebank — mostra a resposta formatada
e os diagnósticos JSON logo abaixo.

Uso:
    python demo/chat_cli.py
    python demo/chat_cli.py --url http://localhost:8000
    python demo/chat_cli.py --full       # imprime o JSON inteiro (não só diagnósticos)
    python demo/chat_cli.py --no-color   # desliga ANSI
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


class C:
    """Códigos ANSI. Setados pra string vazia se --no-color."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    GREY = "\033[90m"

    @classmethod
    def disable(cls) -> None:
        for k in list(vars(cls)):
            if k.isupper():
                setattr(cls, k, "")


BANNER = """
╭──────────────────────────────────────────────────────╮
│   Banco Seguro — Atendimento Virtual (com guardrail) │
╰──────────────────────────────────────────────────────╯
"""

GREETING = "Olá! Sou o assistente virtual do Banco Seguro. Posso te ajudar com dúvidas sobre cartões, PIX, investimentos, empréstimos e mais. Como posso te ajudar hoje?"

HELP_TEXT = """\
Comandos:
  /help      mostra esta ajuda
  /clear     limpa a tela
  /full      alterna entre modo resumido e JSON completo
  /quit      sai (Ctrl+D também funciona)
"""


def post_chat(url: str, message: str, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        url=f"{url.rstrip('/')}/chat",
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fmt_latency(latency: dict | None) -> str:
    if not latency:
        return "-"
    parts = []
    for key in ("input_guard", "retrieve", "generate", "output_guard"):
        v = latency.get(key)
        if v is None:
            continue
        parts.append(f"{key}={v:.0f}ms")
    total = latency.get("total")
    if total is not None:
        parts.append(f"{C.BOLD}total={total:.0f}ms{C.RESET}")
    return " ".join(parts)


def render_response(payload: dict) -> None:
    blocked = bool(payload.get("blocked"))
    response = payload.get("response") or ""
    diag = payload.get("diagnostics") or {}

    if blocked:
        rule = diag.get("rule_violated") or payload.get("category") or "policy"
        validator = diag.get("validator") or "guardrail"
        print(f"{C.RED}{C.BOLD}🛑 BLOQUEADO{C.RESET} {C.DIM}({validator} · {rule}){C.RESET}")
        if response:
            print(f"{C.RED}bot>{C.RESET} {response}")
    else:
        print(f"{C.GREEN}bot>{C.RESET} {response}")


def render_diagnostics(payload: dict, full: bool) -> None:
    diag = payload.get("diagnostics") or {}
    print(f"\n{C.GREY}── diagnostics ──────────────────────────────────────{C.RESET}")
    if full:
        print(f"{C.DIM}{json.dumps(payload, ensure_ascii=False, indent=2)}{C.RESET}")
        return

    rid = diag.get("request_id", "-")
    val = diag.get("validator")
    rule = diag.get("rule_violated")
    sev = diag.get("severity")
    latency = fmt_latency(diag.get("latency_ms"))
    chunks = diag.get("retrieved_chunks") or []
    block = diag.get("block_details")

    print(f"{C.DIM}request_id{C.RESET} {rid}")
    if val or rule or sev:
        print(f"{C.DIM}validator {C.RESET}{val or '-'}   {C.DIM}rule{C.RESET} {rule or '-'}   {C.DIM}severity{C.RESET} {sev or '-'}")
    print(f"{C.DIM}latency   {C.RESET}{latency}")
    if chunks:
        print(f"{C.DIM}rag_chunks{C.RESET} {len(chunks)} hit(s)")
        for i, c in enumerate(chunks[:2], 1):
            preview = (c[:120] + "…") if len(c) > 120 else c
            print(f"  {C.DIM}#{i}{C.RESET} {preview}")
    if block:
        print(f"{C.DIM}block_details{C.RESET}")
        print(f"{C.DIM}{json.dumps(block, ensure_ascii=False, indent=2)}{C.RESET}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat CLI pro guardrail-safebank")
    parser.add_argument("--url", default=os.environ.get("API_URL", "http://localhost:8000"))
    parser.add_argument("--full", action="store_true", help="Mostra o JSON completo por padrão")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        C.disable()

    full_mode = args.full
    print(f"{C.CYAN}{BANNER}{C.RESET}")
    print(f"{C.DIM}endpoint={args.url}  modo={'JSON completo' if full_mode else 'resumido'}  (/help){C.RESET}\n")
    print(f"{C.GREEN}bot>{C.RESET} {GREETING}\n")

    while True:
        try:
            msg = input(f"{C.BLUE}{C.BOLD}você>{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.DIM}Até mais!{C.RESET}")
            return 0
        if not msg:
            continue

        if msg in {"/quit", "/exit", ":q"}:
            print(f"{C.DIM}Até mais!{C.RESET}")
            return 0
        if msg == "/help":
            print(HELP_TEXT)
            continue
        if msg == "/clear":
            os.system("clear")
            continue
        if msg == "/full":
            full_mode = not full_mode
            print(f"{C.DIM}modo agora: {'JSON completo' if full_mode else 'resumido'}{C.RESET}")
            continue

        print(f"{C.DIM}…pensando…{C.RESET}", end="\r", flush=True)
        try:
            payload = post_chat(args.url, msg, timeout=args.timeout)
        except urllib.error.URLError as exc:
            print(" " * 40, end="\r")
            print(f"{C.RED}erro de rede:{C.RESET} {exc}")
            continue
        except json.JSONDecodeError as exc:
            print(" " * 40, end="\r")
            print(f"{C.RED}resposta inválida:{C.RESET} {exc}")
            continue
        print(" " * 40, end="\r")

        render_response(payload)
        render_diagnostics(payload, full_mode)
        print()


if __name__ == "__main__":
    sys.exit(main())
