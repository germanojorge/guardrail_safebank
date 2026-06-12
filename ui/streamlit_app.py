from __future__ import annotations

import os
from typing import Any

import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")
CHAT_TIMEOUT = 60.0

GREETING = "Olá! Sou o assistente virtual do Banco Seguro. Posso te ajudar com dúvidas sobre cartões, PIX, investimentos, empréstimos e mais. Como posso te ajudar hoje?"

RAG_PRESETS: list[tuple[str, str]] = [
    ("PIX vs DOC", "Qual a diferença entre o PIX e o DOC?"),
    ("Cartão rotativo", "Como funciona o crédito rotativo do cartão?"),
    ("Aplicações", "Quais são os tipos de aplicações financeiras?"),
    ("Tarifas", "Quais tarifas bancárias existem?"),
]

st.set_page_config(
    page_title="Banco Seguro — Assistente Virtual",
    page_icon="🏦",
    layout="wide",
)

st.title("Banco Seguro — Assistente Virtual")
st.subheader("Guardrail Bancário · Demo RAG")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": GREETING, "greeting": True}]

if "show_diagnostics" not in st.session_state:
    st.session_state.show_diagnostics = True

if "show_raw_json" not in st.session_state:
    st.session_state.show_raw_json = False

if "pending_message" not in st.session_state:
    st.session_state.pending_message = None


def _health_status() -> str:
    import httpx

    try:
        r = httpx.get(f"{API_URL}/health", timeout=3.0)
        return "Online" if r.status_code == 200 else "Offline"
    except Exception:
        return "Offline"


def _chunk_payload(chunk: Any) -> dict[str, Any]:
    if isinstance(chunk, dict):
        return chunk
    return {"text": str(chunk), "score": None, "source": None}


def _chunk_title(text: str, index: int) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            return line.removeprefix("## ").strip()
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    preview = text.strip().replace("\n", " ")
    if len(preview) > 60:
        preview = preview[:57] + "..."
    return preview or f"Chunk {index}"


def _chunk_preview(text: str, limit: int = 200) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def _render_chunks(chunks: list[Any]) -> None:
    st.markdown(f"**{len(chunks)} chunk(s) recuperado(s)**")
    for i, raw in enumerate(chunks, start=1):
        chunk = _chunk_payload(raw)
        text = chunk.get("text") or ""
        title = _chunk_title(text, i)
        score = chunk.get("score")
        source = chunk.get("source")
        meta_parts = []
        if score is not None:
            meta_parts.append(f"score **{float(score):.3f}**")
        if source:
            meta_parts.append(f"fonte `{source}`")
        label = f"Chunk {i}: {title}"
        with st.expander(label, expanded=i == 1):
            if meta_parts:
                st.caption(" · ".join(meta_parts))
            st.markdown(_chunk_preview(text, limit=10_000))


def _render_diagnostics(msg: dict) -> None:
    diag = msg.get("diagnostics") or {}
    latency = diag.get("latency_ms") or {}

    request_id = diag.get("request_id")
    if request_id:
        st.code(str(request_id), language=None)

    rows = [
        ("input_guard", latency.get("input_guard")),
        ("retrieve", latency.get("retrieve")),
        ("rerank", latency.get("rerank")),
        ("generate", latency.get("generate")),
        ("output_guard", latency.get("output_guard")),
        ("total", latency.get("total")),
    ]
    st.table(
        {
            "Etapa": [r[0] for r in rows],
            "ms": [f"{r[1]:.1f}" if r[1] is not None else "—" for r in rows],
        }
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Categoria:** {diag.get('validator', '—')}")
    with col2:
        st.markdown(f"**Severidade:** {diag.get('severity', '—')}")
    with col3:
        st.markdown(f"**Regra:** {diag.get('rule_violated', '—')}")

    chunks = diag.get("retrieved_chunks")
    if chunks:
        _render_chunks(chunks)

    if diag.get("block_details"):
        st.markdown("**Detalhes do bloqueio**")
        details = diag["block_details"]
        reasoning = details.get("reasoning")
        if reasoning:
            st.info(str(reasoning))
        st.json(details)

    if st.session_state.show_raw_json:
        st.markdown("**JSON completo**")
        st.json(diag)


def _submit_message(prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})

    import httpx

    try:
        with st.spinner("Recuperando contexto + gerando resposta..."):
            r = httpx.post(
                f"{API_URL}/chat",
                json={"message": prompt},
                timeout=CHAT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Serviço indisponível. Tente novamente mais tarde.",
                "blocked": True,
                "category": "error",
            }
        )
        return

    diagnostics = data.get("diagnostics") or {}
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": data.get("response", ""),
            "blocked": data.get("blocked", False),
            "category": data.get("category"),
            "rule_violated": diagnostics.get("rule_violated"),
            "diagnostics": diagnostics,
        }
    )


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            if msg.get("greeting"):
                st.write(msg["content"])
                continue

            blocked = msg.get("blocked", False)
            if blocked:
                category = msg.get("category", "")
                st.error(f"🚫 BLOQUEADO [{category}]")
                rule = msg.get("rule_violated")
                if rule:
                    st.caption(f"Regra violada: {rule}")
                st.write(msg["content"])
            else:
                st.success("✅ OK")
                st.write(msg["content"])

            show_diag = st.session_state.show_diagnostics or blocked
            if show_diag and msg.get("diagnostics"):
                with st.expander("Diagnósticos", expanded=blocked or st.session_state.show_diagnostics):
                    _render_diagnostics(msg)
        else:
            st.write(msg["content"])

if st.session_state.pending_message:
    prompt = st.session_state.pending_message
    st.session_state.pending_message = None
    _submit_message(prompt)
    st.rerun()

if prompt := st.chat_input("Digite sua mensagem..."):
    _submit_message(prompt)
    st.rerun()

with st.sidebar:
    st.header("Perguntas RAG")
    st.caption("Presets alinhados ao FAQ BACEN Itaú (`Itau-Unibanco/FAQ_BACEN`)")
    for label, message in RAG_PRESETS:
        if st.button(label, use_container_width=True):
            st.session_state.pending_message = message
            st.rerun()

    st.divider()
    st.header("Configurações")
    st.session_state.show_diagnostics = st.checkbox(
        "Exibir modo diagnóstico",
        value=st.session_state.show_diagnostics,
    )
    st.session_state.show_raw_json = st.checkbox(
        "JSON bruto nos diagnósticos",
        value=st.session_state.show_raw_json,
    )
    if st.button("Limpar conversa"):
        st.session_state.messages = [{"role": "assistant", "content": GREETING, "greeting": True}]
        st.rerun()

    st.divider()
    st.markdown("**Status da API**")
    status = _health_status()
    if status == "Online":
        st.caption(f"🟢 API: {status}")
    else:
        st.caption(f"🔴 API: {status}")
    st.caption(f"Endpoint: {API_URL}")
