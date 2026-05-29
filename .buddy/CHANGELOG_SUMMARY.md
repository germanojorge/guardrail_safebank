🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Recent Changes (Human-Friendly)

> Resumo em linguagem simples dos últimos commits. Atualizado em 2026-05-29 (HEAD = `189773c`).

## Branch atual: `feature/scrum-17-jailbreak-v3-pos-semantic-out-of-scope`

Os commits desta branch focam em **duas frentes**: defesa em camadas do jailbreak v3 (POS + semântico) e validator novo de "fora de escopo".

## Últimos 15 commits

- **`189773c` chore** — Arquiva plano de demo-itau + relatório de implementação (limpeza).
- **`47b8cc9` test** — Testes unitários pros detectores rule-based + teste de integração do `RuleBasedComplianceValidator`.
- **`9d5a598` feat** — Pipeline de ingestão do FAQ do Itaú (`Itau-Unibanco/FAQ_BACEN`) com coleção Qdrant separada (`itau_faq`).
- **`0cb7481` feat** — `RuleBasedComplianceValidator` + 4 detectores rule-based PT-BR (`data_leak`, `financial_advice`, `fraud`, `out_of_scope`).
- **`f961582` feat** — Switch `LLM_PROVIDER`: modo `mock` usa o `RuleBasedComplianceValidator` (CI sem segredos, demo offline).
- **`46235a3` docs(demo)** — Cartilha de bolso + Beat 4 mais robusto + Beat 3 restaurado.
- **`0d2b6ca` fix(docker)** — Habilita a stack SCRUM-17: instala `pt_core_news_lg` + flags `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`.
- **`ec5b214` docs** — Atualiza `LIMITATIONS.md` e `README.md` com defesa em camadas + out-of-scope.
- **`a36b619` feat(SCRUM-17)** — Jailbreak v3 layered (POS + semantic) + `OutOfScopeValidator`.
- **`9be3f02` chore** — Remove reviews antigos e scripts de demo PII obsoletos.
- **`e640ecb` chore** — Adiciona seção de Git Workflow no `CLAUDE.md` (regras de commit/push).
- **`575fabc` feat** — Regex PII + documentos de review + slides.
- **`e38468b` feat(pii)** — Presidio NER + checksums + endpoint `output-guard` + limpeza de cache.
- **`587b735` fix(demo)** — Resolve 10 blockers achados no ensaio — stack 100% operacional.
- **`811d767` feat(SCRUM-16)** — Tooling de ensaio: arquivos `.http`, robô auto-demo, teste de consistência, sensibilidade do Beat 4.

## Temas dos últimos 30 dias

1. **Defesa em camadas no jailbreak** (SCRUM-17) — substring → Prompt-Guard-2 → POS tagger → semantic similarity. Justificativa: substring sozinho falhava >80% no JailbreakBench parafraseado.
2. **Validator novo: `out_of_scope`** — bloqueia perguntas que não são bancárias antes de chegar no LLM.
3. **Modo mock** (`LLM_PROVIDER=mock`) — permite rodar CI e demos sem chave Anthropic, com `RuleBasedComplianceValidator`.
4. **Ingestão alternativa do Itaú FAQ** — coleção `itau_faq` com dados reais de FAQ bancário (BACEN).
5. **Demo polida** — robô auto-demo, teste de consistência, Beat 4 mais robusto, cartilha de bolso.
6. **PII reforçada** — Presidio NER + checksums Luhn/CPF + endpoint dedicado de output-guard.

## Arquivos modificados/criados desde o último indexed commit

> Vê `git status` abaixo. As mudanças locais (ainda não commitadas) reescreveram parte do `data/banking_kb/`: renomearam os MDs e atualizaram o `06_financiamento_imobiliario.md`. Também modificaram `demo/01-happy.*`, `docker-compose.yml` e `scripts/ingest_itau_faq.py`. Há um `demo/chat_cli.py` novo (untracked).
