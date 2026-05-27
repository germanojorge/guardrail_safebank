# Roteiro de Walkthrough do Código — Apresentação

> Ordem de navegação pelos arquivos seguindo o **caminho de uma requisição**.
> A lógica: entrada → como flui → quem decide → quem fala com o mundo → como observo → como provo que é sério.

```
app.py → state.py → graph.py → nodes.py → validators/ → adapters/ → logger.py → tests+LIMITATIONS+adr
(entrada) (estado)  (orquestra) (nós)     (NÚCLEO)     (fronteiras) (observa)   (rigor)
```

Cada seção tem uma **frase de transição** no fim pra não dar silêncio entre arquivos.

---

## 1. `guardrails/api/app.py` — comece aqui (porta de entrada)

- **`create_app` + `POST /chat` (linha 105)** — "É um proxy. Toda requisição entra aqui e chamo `graph.ainvoke`. Sempre retorno **HTTP 200** — bloqueio é decisão de política, não erro; quem distingue é o campo `blocked` no corpo."
- **`lifespan` (linha 77)** — "Carrego os modelos **uma vez** no startup e guardo em `app.state`. Por isso `workers=1`: ~1.5GB de modelo, não quero duplicar por worker."
- **`_create_components` (linha 24)** — "Separei essa factory de propósito: nos testes patcheio **uma** chamada em vez de cada construtor."
- **middleware `request_id` (linha 94)** — "Todo request ganha um UUID amarrado no log via contextvars — rastreabilidade."

➡️ *"Mas o `/chat` só delega pro grafo. O coração está na pipeline."*

---

## 2. `guardrails/pipeline/state.py` — o estado que flui

- "Esse `GraphState` é o objeto que percorre todos os nós acumulando campos: `blocked`, `block_category`, `diagnostics`. As categorias e o `SEVERITY_MAP` também moram aqui." (arquivo curto, abre rápido)

---

## 3. `guardrails/pipeline/graph.py` — orquestração (decisão central)

- **`build_graph` + edges (linha 89-103)** — "Aqui está o porquê de LangGraph: o fluxo é literalmente um grafo. `input_guard → (passa?) → retrieve → generate → output_guard`. As branches pass/bloqueia são **conditional edges** (`route_after_input`/`route_after_output`). Mapeiam 1:1 no problema."
- **Injeção de dependência** — "Todo validator é opcional no construtor; se não injeto, cria o default. Isso me dá testabilidade."

➡️ *"Os nós são funções Python puras — vamos ver o que cada um faz."*

---

## 4. `guardrails/pipeline/nodes.py` — os nós

- **`input_guard` (linha 43)** — "Roda 3 validators em sequência; no primeiro que falha, loga, marca `blocked` e retorna — **short-circuit**, não desperdiço o LLM."
- **`retrieve` (linha 88)** — emendar o RAG aqui (ver §6 adapters).
- **`generate` (linha 122)** — "Monta o prompt com os chunks + pergunta e chama o chatbot."
- **`output_guard` (linha 146)** — "Mesmo padrão, mas na **resposta do LLM**: toxic, pii_output e o compliance judge."
- "Cada nó cronometra a si mesmo em `diagnostics` — é daí que sai o breakdown de latência da demo."

➡️ *"O grafo orquestra, mas quem valida são os validators. Esse é o núcleo técnico."*

---

## 5. `guardrails/validators/` — o NÚCLEO (gaste mais tempo aqui)

Ordem de profundidade crescente:

1. **`base.py`** — "Contrato comum: todo validator é `run(text) -> ValidatorResult`. Detalhe: `score` **não é comparável** entre validators, e está documentado."
2. **`pii.py` + `_pii_patterns.py`** — "Regex puro. `_pii_patterns.py` é fonte única — o **mesmo** padrão valida e redige no log, pra não dar drift."
3. **`toxic.py`** — "detoxify, pego o maior dos 5 sub-scores vs threshold. **Fail-closed** na linha 42: se o modelo falha, bloqueio."
4. **`jailbreak.py`** — DESTAQUE. "Defesa em **camadas**: substring fast-path (linha 91) pega o óbvio em <5ms; se passa limpo, cai no DeBERTa (linha 126). O campo `layer_caught` diz qual camada pegou."
5. **`compliance.py` + `compliance/rubric.py`** — O KILLER. "Único LLM-as-Judge. Forço `tool_use` (linha 94) pra saída estruturada, `temperature=0`, e **prompt caching** na rubrica. A `rubric.py` tem as 5 regras BACEN/CVM com few-shots."

➡️ *"Tudo que toca o mundo externo está atrás de um adapter."*

---

## 6. `guardrails/adapters/` — as fronteiras (narrativa AWS)

- **`llm.py`** — "`LLMProvider` é um Protocol. `AnthropicProvider` é só uma implementação. **É assim que migro pra Bedrock**: troco a implementação, o resto não muda."
- **`embedding.py`** — "E5 local; aplico os prefixos `query:`/`passage:` internamente."
- **`vector_store.py`** — "Qdrant + um `InMemoryVectorStore` fake pra testes. Conexão lazy: se o Qdrant cai, `/health` degrada em vez de derrubar a API."

➡️ *"E tudo isso é observável."*

---

## 7. `guardrails/observability/logger.py` — observabilidade

- "structlog em JSON no stdout, lido com `jq`. Dois detalhes de segurança: nunca logo texto cru — guardo um `input_hash` e um `snippet` que passa pelo `sanitize_for_log`, que **redige PII** usando as mesmas regex."

---

## 8. `tests/` + `LIMITATIONS.md` + `adr/` — o rigor (feche aqui)

"Não é só código que roda — é código com rigor declarado."

- `tests/adversarial/` com fixtures de **fonte externa** (JailbreakBench, HateBR).
- `LIMITATIONS.md` — o que cada guardrail reconhecidamente **não** pega.
- `adr/001..006` — o porquê de cada decisão.

---

## Perguntas prováveis (prepare estas — entrevista se ganha aqui)

| Pergunta | Resposta (e onde está) |
|---|---|
| "Por que não usou a lib `guardrails-ai`?" | ADR 001 — controle total; integração com LangGraph era só LCEL (irrelevante). Decisão, não preguiça. |
| "Regex pra PII? E nome/endereço?" | LIMITATIONS — sei dos gaps (sem checksum, sem NER). Presidio é o próximo passo. Escolha consciente por prazo. |
| "Como escala? Por que 1 worker?" | LIMITATIONS §Infra — modelos ~1.5GB não duplicam por worker. Em prod: modelos em serviço próprio, autoscale, ALB. |
| "Como testa um LLM-judge sem ser circular?" | Loop fechado **declarado**. Fonte externa onde dava (JailbreakBench, HateBR). Calibração humana no roadmap. |
| "E AWS / Bedrock?" | Adapter pronto. Migração é trocar a implementação do `LLMProvider`. Fora do MVP por prazo. |
| "Quanto custa rodar?" | ~$0.0001/req (Haiku + prompt caching no system prompt da rubrica). |

> Dizer **espontaneamente** que as fixtures de compliance são loop fechado (`closed_loop: true`) vale ouro: mostra que você conhece o viés do próprio trabalho. Honestidade sobre limites = sinal sênior.
