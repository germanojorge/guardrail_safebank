🏠 [Home](../README_FOR_HUMANS.md) · [Getting Started](../GETTING_STARTED.md) · [Architecture](../ARCHITECTURE.md) · [Tech](../TECH_STACK.md) · [Integrations](../INTEGRATIONS.md) · [Repo Map](../MAP/repo_map.md) · [Links](../LINKS.md)

---

# Assumptions

> Coisas que o Buddy *deduziu* mas não verificou linha-por-linha. **Não são fatos.** Confira antes de confiar.

## Pipeline

1. **Ordem dos validators no `input_guard`** assumida como `toxic → pii → out_of_scope → jailbreak`. Pode ser outra; verificar em `guardrails/pipeline/nodes.py`.
2. **Ordem no `output_guard`** assumida como `toxic → pii → compliance`. Verificar idem.
3. **Compliance Judge é o único validator com chamada de rede.** Os demais (toxic, pii, jailbreak) são local. Verificar — mas é a intenção do design (ver ADR 003).

## Modo mock

4. Assumi que `LLM_PROVIDER=mock` também faz o `AnthropicProvider` virar stub (chatbot canned). Verificar em `guardrails/adapters/llm.py` se há código `if provider == "mock"`. Pode ser que só o judge troque, e o chatbot continue chamando Anthropic.

## Caching de modelos

5. Assumi que `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` exigem cache pré-populado no host. Se cache vazio, build do container vai falhar — não verificado em ambiente limpo.

## Limites de bloqueio

6. **Block rate ≥80%** mencionado no README aplica-se a *jailbreak* e *toxicidade* nos testes adversariais. PII e compliance podem ter threshold próprio. Verificar `tests/adversarial/`.

## Decisões revertidas

7. ADR 005 diz "regex puro PT-BR" mas código tem Presidio NER (ver `NOTES/open_questions.md` #1). Assumo que a realidade pesa mais que o ADR, mas o ADR pode ser intencionalmente mantido como "decisão histórica".
