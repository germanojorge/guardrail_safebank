🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Important Links

> Docs externos, design docs, runbooks. Tudo que um colega gostaria de saber.

Adicionar pelo terminal:

```bash
buddy link https://example.com/doc --title "Título" --tags architecture,banking --relevance must-read
```

> ⚠️ O Buddy nunca lê o conteúdo da URL — só guarda metadados. Pra resumir, cola o texto aqui no chat.

---

## Must-read

### Internos do repo (não são URLs externas, mas valem destaque)

- [`CLAUDE.md`](../CLAUDE.md) — Briefing, decisões, tabela requisito-da-vaga × feature. Por que matters: contexto denso do projeto inteiro.
- [`README.md`](../README.md) — Storyboard da demo de 8 min + ASCII da arquitetura.
- [`LIMITATIONS.md`](../LIMITATIONS.md) — Onde o sistema *sabe* que falha. Por que matters: anti loop fechado; honesto sobre gaps.
- [`.claude/agents/PRDs/PRD.md`](../.claude/agents/PRDs/PRD.md) — PRD v2.0 (autoritativo para escopo do MVP).
- [`adr/001` → `adr/006`](../adr/) — 6 ADRs com o porquê das escolhas.

## Helpful

### Bibliotecas / docs externos relevantes

| URL | Pra que |
|---|---|
| <https://langchain-ai.github.io/langgraph/> | LangGraph (orquestrador) |
| <https://docs.anthropic.com/> | Claude SDK + tool_use (usado no Compliance Judge) |
| <https://qdrant.tech/documentation/> | Qdrant (vector store) |
| <https://huggingface.co/intfloat/multilingual-e5-small> | Embedder local |
| <https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M> | Jailbreak classifier (gated) |
| <https://huggingface.co/unitary/multilingual-toxic-xlm-roberta> | detoxify modelo multilingual |
| <https://github.com/JailbreakBench/jailbreakbench> | Fixtures adversariais |
| <https://huggingface.co/datasets/Itau-Unibanco/FAQ_BACEN> | Dataset FAQ Itaú (RAG real) |

## Optional

*(vazio)*
