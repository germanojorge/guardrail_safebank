# Oi! 👋 Bem-vindo ao Guardrail SafeBank

Sou o **Buddy**. Este é o seu cantinho pra entender o projeto sem se perder. Vou explicar como se você estivesse vendo tudo pela primeira vez.

---

## O que é este projeto?

- **O que ele faz:** É um "porteiro" inteligente que fica na frente de um chatbot bancário. Toda mensagem que o cliente manda passa por ele antes de chegar ao Claude (o LLM da Anthropic). E toda resposta que o Claude gera também passa por ele antes de voltar pro cliente. Se algo perigoso aparecer (vazamento de CPF, tentativa de "hackear" o robô, conselho financeiro proibido), o Buddy bloqueia.
- **Quem usa:** Foi criado como projeto de entrevista técnica. O "usuário final imaginário" é um banco brasileiro (B2C) que quer um chatbot seguro. Quem trabalha no código são engenheiros que querem entender como montar guardrails de LLM na prática.
- **Por que existe:** Pra mostrar, num caso real e em português, como combinar várias técnicas (regex, modelos pequenos do HuggingFace, LLM-as-a-Judge, RAG) num pipeline que dá pra rodar com `docker compose up`.

## Ideias grandes que você precisa saber antes de ler código

1. **É um proxy bidirecional.** Não é o chatbot. É o que fica **entre** o cliente e o chatbot. Intercepta os dois lados.
2. **LangGraph é só o "trilho do trem".** Ele organiza os nós (input guard → retrieve → generate → output guard) num grafo. Os validators em si são funções Python puras.
3. **Cada validator tem uma especialidade.**
   - `toxic` → modelo `detoxify` multilíngue.
   - `pii` → regex PT-BR (email, telefone, CPF, cartão) + Presidio NER opcional. Roda na entrada **e** na saída.
   - `jailbreak` → defesa em camadas: substring rápido + Prompt-Guard-2 (HF) + tagger POS + semântico.
   - `out_of_scope` → checa se a pergunta é sobre banco mesmo.
   - `compliance` → o único que usa LLM: Claude Haiku como juiz, com uma rubrica de 5 regras (R1–R5).
4. **Modo "mock" sem API.** Se você não tiver chave da Anthropic, defina `LLM_PROVIDER=mock` e o juiz vira um conjunto de regras determinísticas (`RuleBasedComplianceValidator`).
5. **RAG é simples.** Qdrant + `intfloat/multilingual-e5-small` (sentence-transformers, local). Documentos PT-BR em `data/banking_kb/`.

## Links rápidos

- 🚀 **Só quer rodar?** → [`GETTING_STARTED.md`](./GETTING_STARTED.md)
- 🗺️ **Onde mora cada coisa?** → [`MAP/repo_map.md`](./MAP/repo_map.md)
- 🏛️ **Como tudo se encaixa?** → [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- 🧰 **Que tecnologia usa?** → [`TECH_STACK.md`](./TECH_STACK.md)
- 🔌 **Com quem ele conversa?** → [`INTEGRATIONS.md`](./INTEGRATIONS.md)
- 📎 **Links externos importantes** → [`LINKS.md`](./LINKS.md)
- ❓ **O que o Buddy ainda não tem certeza** → [`NOTES/open_questions.md`](./NOTES/open_questions.md)

---

## Como usar o Buddy

No terminal:
- `buddy status` — O conhecimento aqui está atualizado?
- `buddy precheck` — Mostra documentos que podem estar desatualizados.
- `buddy open <name>` — Abre um doc do Buddy (ex.: `buddy open getting-started`).
- `buddy link <url>` — Salva um link importante (oculta segredos).

No Copilot CLI (depois de `buddy agent` e `/agents add buddy`):
- *"Atualiza o buddy com as minhas mudanças"* (antes de commitar)
- *"Onde mora a lógica do guard de saída?"*
- *"Como o Beat 4 da demo funciona?"*

> **Dica do Buddy:** o arquivo mais denso de contexto deste repo é o [`CLAUDE.md`](../CLAUDE.md) na raiz. Ele tem a tabela de decisões, o backlog de Extras e o mapeamento requisito-da-vaga → feature. Vale a leitura.
