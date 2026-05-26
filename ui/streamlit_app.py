from __future__ import annotations

import os

import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Banco Seguro — Assistente Virtual",
    page_icon="🏦",
    layout="wide",
)

st.title("Banco Seguro — Assistente Virtual")
st.subheader("Guardrail Bancário · Demo")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "show_diagnostics" not in st.session_state:
    st.session_state.show_diagnostics = True


def _health_status() -> str:
    import httpx

    try:
        r = httpx.get(f"{API_URL}/health", timeout=3.0)
        return "Online" if r.status_code == 200 else "Offline"
    except Exception:
        return "Offline"


def _render_diagnostics(msg: dict) -> None:
    diag = msg.get("diagnostics") or {}
    latency = diag.get("latency_ms") or {}

    rows = [
        ("input_guard", latency.get("input_guard")),
        ("retrieve", latency.get("retrieve")),
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
    if diag.get("block_details"):
        st.json(diag["block_details"])
    chunks = diag.get("retrieved_chunks")
    if chunks:
        st.markdown("**Chunks recuperados:**")
        for c in chunks:
            st.markdown(f"- {c}")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
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
            if show_diag:
                with st.expander("Diagnósticos", expanded=False):
                    _render_diagnostics(msg)
        else:
            st.write(msg["content"])

if prompt := st.chat_input("Digite sua mensagem..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    import httpx

    try:
        with st.spinner("Consultando assistente..."):
            r = httpx.post(
                f"{API_URL}/chat",
                json={"message": prompt},
                timeout=15.0,
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
        st.rerun()

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
    st.rerun()

with st.sidebar:
    st.header("Configurações")
    st.session_state.show_diagnostics = st.checkbox(
        "Exibir modo diagnóstico",
        value=st.session_state.show_diagnostics,
    )
    if st.button("Limpar conversa"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.markdown("**Status da API**")
    status = _health_status()
    if status == "Online":
        st.caption(f"🟢 API: {status}")
    else:
        st.caption(f"🔴 API: {status}")
    st.caption(f"Endpoint: {API_URL}")
