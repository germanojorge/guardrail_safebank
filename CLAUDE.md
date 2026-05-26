# Guardrail Bancário — Projeto de Entrevista Técnica

> **Atualizado 2026-05-25** alinhado com PRD v2.0 em `.claude/agents/PRDs/PRD.md`. Tabela "Decisões" e diagrama refletem decisões do grilling de 2026-05-25: abandono de `guardrails-ai` (biblioteca), remoção de Presidio, troca Voyage→sentence-transformers, troca Langfuse→JSON logs, Compliance Judge re-confirmado no MVP, jailbreak em camadas (substring + DeBERTa), PII no input E output, rescope de 3→2 dias.

## Ideia do Projeto

**Guardrail bancário** (proxy LangGraph + FastAPI) com validators custom em Python puro para filtrar:
- Conteúdo tóxico (detoxify)
- PII (regex PT-BR — input e output)
- Prompt injection / jailbreak (substring fast-path + DeBERTa HF, em camadas)
- Compliance bancário (LLM-as-Judge com rubrica de 5 regras — único caso sem solução determinística)

## Decisões Já Tomadas

| Decisão | Status |
|---|---|
| **spec-kit** para spec-development | Abandonado (2026-05-24) — produziu volume de artefato sem rigor; ver HANDOFF.md e [building-rigorously.md](file:///home/germano/.claude/rules/building-rigorously.md) §8 |
| **`guardrails-ai`** como biblioteca base | **Abandonado (2026-05-25)** — controle total do pipeline; menos dependência pesada; LangGraph + Anthropic SDK + validators custom em Python cobrem o caso sem mágica escondida. Integração com LangGraph era apenas `guard.to_runnable()` (LCEL), irrelevante quando o orquestrador é LangGraph. Re-introduzir = Extras |
| **Prazo MVP: 2 dias úteis** (entrega 2026-05-27) | Definido (2026-05-25) — rescope de 4 → 3 → 2 dias |
| **Docker** para containerização | Definido |
| **CI/CD** com boas práticas | Definido (GitHub Actions — lint ruff + pytest + adversarial smoke + docker build) |
| **Deployment local apenas (Docker)** — AWS/Bedrock fora de escopo do MVP | Definido (2026-05-24) — AWS vira narrativa verbal usando o hook de abstração de provider |
| **Arquitetura: proxy/middleware** na frente de chatbot bancário | Definido (2026-05-23) — maior cobertura de requisitos + demo impactante |
| **Caso de uso: atendimento ao cliente B2C** | Definido (2026-05-23) — força os 4 guardrails-chave (PII, injection, toxicidade, compliance), narrativa imediata, RAG fácil de popular |
| **Guardrail bidirecional** — intercepta input do usuário E output do LLM | Definido (2026-05-23) — bloquear PII vazada (input E output), respostas tóxicas, e violações de compliance |
| **Orquestração: LangGraph standalone** (sem LangChain) | Definido (2026-05-23, simplificado 2026-05-25) — pipeline stateful com branches condicionais (passa/bloqueia) mapeia 1:1 em StateGraph. Nodes são funções Python puras; LangChain como dependência extra é desnecessário (text splitters reimplementáveis em <20 LOC; LCEL irrelevante porque branches viraram conditional edges) |
| **Testes adversariais no MVP: dataset estático curado** com fontes externas (anti loop fechado, building-rigorously.md §1) | Definido (2026-05-23, fontes definidas 2026-05-25) — JailbreakBench, HateBR (PT-BR), RealToxicityPrompts; tradução PT-BR via Claude. PII e Compliance Judge fixtures hand-crafted com loop fechado DECLARADO em `LIMITATIONS.md` |
| **Observabilidade: structlog JSON em stdout** (captured by `docker logs`) | Definido (2026-05-25) — Langfuse self-hosted abandonado pra economizar 1 container + ~2-3h. Eventos estruturados (`event, category, severity, rule_violated, input_hash, latency_ms`) com `jq` na demo. Langfuse vira Extras |
| **LLM provider: Anthropic Claude** (Haiku 4.5 para compliance judge, Sonnet 4.6 para chatbot) atrás de adapter | Definido (2026-05-23) — Claude segue rubricas bem, materializa "seleção dinâmica de modelos" do JD, abre narrativa de prompt caching; adapter serve testabilidade + model swap |
| **Vector store: Qdrant via Docker** | Definido (2026-05-23) — open-source, filtros nativos por metadado, encaixa em docker-compose, API simples atrás do adapter |
| **Embeddings: `sentence-transformers/intfloat/multilingual-e5-small` local** | Definido (2026-05-25) — Voyage AI abandonado nesta sprint pra remover dependência de API/quota do caminho crítico da demo. ~120MB, CPU. Voyage vira Extras com ADR explicando trade-off (qualidade PT-BR superior) |
| **PII: regex puro PT-BR** (email, telefone, CPF formatado, cartão 16 dígitos) | Definido (2026-05-25) — Presidio abandonado nesta sprint. Limitações declaradas em `LIMITATIONS.md`: CPF sem checksum, cartão sem Luhn, sem CNPJ, sem conta bancária, sem detecção de nome/endereço. Presidio + CPF/CNPJ/Luhn checksums viram Extras |
| **Jailbreak em camadas (layered defense)** — substring fast-path (do PoC) + DeBERTa HF (`protectai/deberta-v3-base-prompt-injection-v2`) | Definido (2026-05-25) — substring sozinho falha em >80% do JailbreakBench (paraphrased), por isso building-rigorously.md §6 ("substring matching is almost never a guardrail"). Layered defense narrada: tabela com taxa de bloqueio substring-only vs substring+DeBERTa em `LIMITATIONS.md` |
| **AI-as-a-Judge: 1 judge sync (Claude Haiku) para Compliance Bancário** | **Re-confirmado (2026-05-25)** — corte anterior revertido após grilling: implementação é ~2-3h, é o diferencial central da vaga, único validator que justifica LLM. Rubrica de 5 regras (R1-R5) + 2 few-shots por regra; tool use pra structured output (`verdict, rule_violated, reasoning`); bloqueio direto (reask = Extras). Detalhes em `guardrails/compliance/rubric.py` e PRD §7 F-4 |
| **Security Agent: reframe arquitetural** — o próprio pipeline de guardrails é o Security Agent, com block_log node persistindo bloqueios em JSON estruturado | Definido (2026-05-23, observabilidade atualizada 2026-05-25) — evita over-scope; cada guardrail = sub-agente especializado; agente analítico autônomo de detecção de padrões fica em Extras |
| **Divisão de responsabilidades**: LangGraph **orquestra**, validators custom Python **validam**, Compliance é **node próprio** chamando Claude Haiku via Anthropic SDK direto | Definido (2026-05-23, simplificado 2026-05-25) — sem herança de `Validator` do guardrails-ai (biblioteca abandonada); cada validator é função `(text) -> ValidatorResult`. Reask 1x vira Extras (no MVP é bloqueio direto pra previsibilidade e <2h de implementação a menos) |
| **Validators custom em Python**: `toxic` (detoxify), `pii` (regex, in+out), `jailbreak` (substring+DeBERTa), `compliance` (Haiku + rubrica + tool use) | Definido (2026-05-25) — substitui linha anterior de "Validators do Hub guardrails-ai" após pivot. Topic restriction vira Extras |
| **Demo**: FastAPI (proxy real) + Streamlit (cliente com diagnósticos visuais) + Qdrant + Anthropic, tudo via `docker compose up`. Roteiro 8min: setup → caso feliz (Beat 1 cartão Gold) → 3 ataques bloqueados ao vivo (Beat 2 jailbreak DAN, Beat 3 PII CPF, Beat 4 Compliance R2 recomendação financeira indevida) → logs JSON com jq → CI verde → arquitetura | Definido (2026-05-23, storyboard travado 2026-05-25) — Beat 4 é killer: pergunta inocente, resposta plausível, violação sutil → demonstra valor único do LLM judge. Detalhes em PRD §11 e §7 F-6 |
| **API: FastAPI `def` handlers + lifespan + Starlette threadpool**; block = HTTP 200 (policy decision, não erro); único uvicorn worker (modelos ~1.5GB não devem duplicar por worker); `request_id` UUID4 via structlog `contextvars`; `_create_components` factory separada para testabilidade (monkeypatching no CI sem carregar modelos reais) | Definido (2026-05-26) |


## Arquitetura Final (Mental Model)

```
                        ┌─────────────────────────────────────────┐
                        │   FastAPI (proxy)  POST /chat           │
                        └────────────────┬────────────────────────┘
                                         │
                        ┌────────────────▼────────────────────────┐
                        │   LangGraph StateGraph                  │
                        │                                         │
   ┌──────────┐         │   [Input Guard]                         │
   │ Streamlit│────────▶│      ├─ toxic (detoxify)                │
   │ (cliente │         │      ├─ pii (regex PT-BR)               │
   │  + diag) │         │      ├─ jailbreak (substring + DeBERTa) │
   └──────────┘         │      ├─ pass ──▶ [Retrieve]             │
                        │      └─ fail ──▶ [Block + Log]          │
                        │                  │                      │
                        │            [LLM Generation]             │
                        │                  │                      │
                        │      [Output Guard]                     │
                        │      ├─ toxic (detoxify)                │
                        │      ├─ pii (regex — NOVO)              │
                        │      ├─ compliance (Haiku judge + R1-R5)│
                        │      ├─ pass ──▶ Return                 │
                        │      └─ fail ──▶ [Block + Log]          │
                        └─────────────────────────────────────────┘
                                  │              │
                                  ▼              ▼
                              Qdrant         Anthropic
                       (+ sentence-          (Sonnet chatbot,
                        transformers)         Haiku judge)

       Observabilidade: structlog JSON → docker logs (stdout)
       PRD detalhado: .claude/agents/PRDs/PRD.md
```



## Extras (Pós-Demo / Backlog)

Itens deliberadamente fora do MVP para garantir entrega em 2 dias. Cada um cobre algum requisito ou diferencial do JD e pode ser citado na entrevista como **"próximos passos planejados"**, mostrando visão de roadmap.

| Extra | Cobre do JD | Por que ficou fora do MVP |
|---|---|---|
| **Biblioteca `guardrails-ai`** — Hub validators (ToxicLanguage, DetectPII, DetectJailbreak, RestrictToTopic) + reask nativo + interop | "framework de guardrails da indústria" | Pivot 2026-05-25: controle total + reuso do PoC; integração com LangGraph era apenas LCEL (irrelevante). Migração futura mantém adapter dos validators |
| **Presidio Analyzer** + CPF com checksum, CNPJ com checksum, cartão com Luhn, conta bancária | rigor de PII, detecção de nome/endereço via NER PT-BR | Pivot 2026-05-25: regex do PoC + bloqueio cobre os casos de demo; Presidio install + integração custa ~2-3h |
| **Voyage AI embeddings** (`voyage-3`) | parceria oficial Anthropic, qualidade superior PT-BR | Pivot 2026-05-25: sentence-transformers local elimina dep de API/quota no caminho crítico; trade-off de qualidade documentado em ADR 004 |
| **Langfuse self-hosted via Docker** — traces ricos, dashboard ao vivo, OTel exporter | observabilidade profunda, narrativa "banco não manda dado sensível pra SaaS" | Pivot 2026-05-25: JSON logs em stdout cobrem demo; Langfuse adiciona 1 container + ~2-3h |
| **Reask 1x do Compliance Judge** — auto-correção (output viola → LLM reescreve → judge de novo → bloqueia se falhar 2x) | maturidade de LLM-as-Judge, narrativa rica | Tuning de prompt anti-loop custa tempo; bloqueio direto é mais previsível na demo |
| **Topic Restriction validator** — RestrictToTopic ou zero-shot classifier "só assuntos bancários" | "restringir uso indevido" do JD | Cortado em 2026-05-25 pra concentrar tempo no Compliance Judge (mais valor narrativo) |
| **CrewAI Red Team Agent** — agentes colaborativos (gerador + crítico + sintetizador) gerando casos adversariais automatizados | "Red Teaming para LLMs" (diferencial), "agentes multi-LLM", CrewAI | MVP usa dataset estático curado de fontes externas |
| **garak (NVIDIA)** como fuzz testing no CI | red teaming automatizado, ferramenta da indústria | Lento no CI, flaky; complementa adversarial estático |
| **Judge de Groundedness** com claim decomposition + judge LLM contra chunks RAG | mitigação de alucinações, AI-as-a-Judge aprofundado | MVP confia na qualidade do RAG; medição com claim decomposition é próximo passo |
| **Judge async de Helpfulness/Tom** rodando sobre traces | LLMOps, qualidade contínua | MVP só tem judge sync; async exige job adicional fora do path crítico |
| **Calibração do judge contra labels humanos** (~100 casos, Cohen's kappa) | rigor de avaliação | Tempo de curadoria de labels — exige humano no loop |
| **Security Agent analítico autônomo** — agente LangGraph que consome eventos do block_log e detecta padrões (ex: campanha coordenada de ataque) | "Security Agents" (responsabilidade central do JD), detecção avançada | Reframe arquitetural cobre o requisito no MVP; agente analítico é evolução natural |
| **Migração para AWS Bedrock + Deploy AWS** (ChatBedrock, ECS Fargate ou Lambda + API Gateway, OpenSearch como vector store, Titan/Cohere embeddings via Bedrock) | "Amazon Bedrock", "AWS", "ECS, Lambda, S3, OpenSearch, API Gateway" | Rescope; abstração de provider mantém ponte trivial caso reentre em escopo. Narrativa verbal na entrevista usando o hook |
| **Avaliação Agno** ou seleção dinâmica de modelo mais sofisticada (roteamento por complexidade/custo) | "seleção dinâmica de LLMs" (diferencial), Agno | Citar como avaliado mas fora de escopo |
| **Streaming de respostas** com guardrails incrementais (token-by-token) | maturidade de produto LLM | Complexidade alta vs ganho de demo |
| **Dashboards Grafana customizados** | observabilidade aprofundada | JSON logs cobrem demo |
| **Integração com sistema legado simulado** (ex: mock de core bancário REST) | "integração com sistemas legados" (diferencial) | Adiciona escopo sem agregar à narrativa de guardrails |
| **PII masking** ao invés de bloqueio puro | UX mais sofisticada de PII | MVP bloqueia + pede usuário reformular; masking é evolução |
| **Auditoria de docs RAG** pra contaminação de PII (scan no ingestion) | defesa em profundidade | Output guard cobre o caso em runtime |

## Estratégia de Cobertura dos Requisitos

A meta é que o projeto sirva como **ponto de apoio narrativo** para cada item da vaga, mesmo quando a implementação é mínima. Princípio: **profundidade em 2-3 áreas + breadth com hooks claros nas demais.**

Mapeamento (atualizado 2026-05-25):

| Requisito da vaga | Onde aparece no projeto |
|---|---|
| RAG | Qdrant + sentence-transformers + 8 docs sintéticos PT-BR, consultados pelo chatbot |
| Multi-agente | Pipeline de guardrails como sub-agentes especializados (toxic, pii, jailbreak, compliance) |
| LangChain/LangGraph | LangGraph standalone como orquestrador (LangChain não é necessário) |
| Observabilidade | structlog JSON em stdout, breakdown de latência por stage, `docker logs api | jq` |
| LLMOps | Avaliação automatizada no CI com dataset adversarial de fontes externas (JailbreakBench, HateBR, RealToxicityPrompts) |
| AI-as-a-Judge | **Compliance Judge** (Claude Haiku + rubrica R1-R5 + tool use), Beat 4 da demo |
| Prompt injection / jailbreak | Layered defense: substring fast-path + DeBERTa HF; tabela de contribuição em LIMITATIONS.md |
| AWS / Bedrock | **Narrativa verbal**: adapter `LLMProvider`/`EmbeddingProvider`/`VectorStore` + ADR explicando migração; deploy AWS fora do MVP |
| Security Agents | Pipeline de guardrails enquadrado como security agents (cada validator = sub-agente) |
| CI/CD | GitHub Actions com lint ruff + pytest + adversarial smoke + docker build |
| Banking compliance / regulatório | Rubrica R1-R5 do Compliance Judge cobre BACEN/CVM (promessa de rendimento, recomendação específica, ação não-executável, vazamento de instruções, fora do escopo) |
