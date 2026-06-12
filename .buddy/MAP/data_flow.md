🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Data Flow

> Os caminhos típicos pelo sistema, em palavras simples.

## Fluxo 1 — Mensagem normal (caminho feliz)

1. Cliente manda `POST /chat {"message": "Como funciona o cartão Gold?"}`.
2. FastAPI gera `request_id` (UUID4), liga no contexto structlog.
3. **`input_guard`** roda em ordem: `toxic` → `pii_input` → `out_of_scope` → `jailbreak`. Todos retornam `blocked=False`.
4. **`retrieve`** consulta Qdrant (`itau_faq`) com embedding da mensagem (e5-base). Retorna top-k chunks.
5. **`generate`** chama Anthropic (`claude-sonnet-4-6`) com system prompt + chunks + mensagem.
6. **`output_guard`** roda `toxic` → `pii_output` → `compliance` (Haiku judge). Todos passam.
7. Responde HTTP 200 com `{"blocked": false, "response": "...", "diagnostics": {...}}`.
8. structlog emite `guardrail.allowed` com `latency_ms` por estágio.

## Fluxo 2 — Bloqueio na entrada (PII / jailbreak / tox / out_of_scope)

1. `POST /chat {"message": "Meu CPF é 123.456.789-09"}`.
2. **`input_guard`** roda os validators na ordem. `pii_input` detecta CPF.
3. `state["blocked"] = True`, `category = "pii"`, `rule_violated = "cpf"`.
4. Aresta condicional manda direto pro **`block_log`** (pula retrieve, generate, output_guard).
5. `block_log` emite evento JSON com `input_hash` (sha256) — texto cru nunca é logado.
6. HTTP 200 com `{"blocked": true, "category": "pii", "rule_violated": "cpf", "response": "<mensagem padronizada>"}`.

## Fluxo 3 — Bloqueio na saída (compliance R2)

1. `POST /chat {"message": "Qual é o melhor CDB do mercado?"}`.
2. Input guard passa (pergunta inocente, sobre banco, sem PII, sem jailbreak).
3. RAG + Sonnet geram uma resposta plausível ("O CDB do Banco XYZ tem a melhor rentabilidade...").
4. **`output_guard`** → `toxic` passa → `pii_output` passa → `compliance` chama Haiku com a rubrica.
5. Haiku retorna `{"verdict": "block", "rule_violated": "R2", "reasoning": "..."}` via tool_use.
6. Pipeline vai pro `block_log`. HTTP 200 com `blocked=true`, `category=compliance`, `rule_violated=R2`.

## Fluxo 4 — Modo mock (sem Anthropic)

Quando `LLM_PROVIDER=mock`:

1. `_create_components` substitui `ComplianceValidator` por `RuleBasedComplianceValidator`.
2. O judge vira combinação dos detectores em `guardrails/detectors/`: `data_leak`, `financial_advice`, `fraud`, `out_of_scope`.
3. O LLM chatbot é stub (responde texto canned).
4. Útil pra CI sem segredos e demos offline.

## Fluxo 5 — Ingestão do RAG (offline, via perfil compose)

1. `docker compose run --rm ingest` invoca `scripts/ingest_itau_faq.py`.
2. Script carrega `Itau-Unibanco/FAQ_BACEN` (split train), embeda com sentence-transformers, e popula a coleção `itau_faq` no Qdrant.
3. Split test fica em `data/eval/faq_bacen_eval.jsonl` para avaliação de retrieval.

## Fluxo 6 — Observabilidade

Cada bloqueio/permissão emite um evento structlog em JSON pra stdout:

```json
{
  "event": "guardrail.blocked",
  "category": "jailbreak",
  "severity": "high",
  "rule_violated": "jailbreak",
  "input_hash": "sha256:abc...",
  "request_id": "uuid4-...",
  "latency_ms": {
    "input_guard": 12.3,
    "retrieve": 1.1,
    "generate": 830.5,
    "output_guard": 45.2,
    "total": 889.1
  }
}
```

Captura: `docker logs api | jq`. Sem PII vaza — só hashes.
