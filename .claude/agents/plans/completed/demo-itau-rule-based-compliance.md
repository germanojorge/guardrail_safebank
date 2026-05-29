# Demo Itaú sem-LLM-Judge + Itaú FAQ no RAG

## Context

A entrevista com o Itaú é **2026-05-30 (amanhã)**. A demo precisa rodar de forma robusta e, principalmente, o **Compliance Judge não dependerá mais do Claude Haiku** — vamos substituí-lo por uma camada de detectores rule-based portada do projeto anterior do usuário (`germanojorge/guardrail-bancario`). O chatbot continua usando Sonnet 4.6 (escopo confirmado pelo usuário).

Problemas resolvidos por esta mudança:
1. **Compliance previsível na demo**: regras determinísticas (fraud, financial_advice, data_leak, out_of_scope) ao invés de um judge LLM que pode oscilar/lentidão.
2. **Tornar o RAG narrativo para o Itaú**: hoje o RAG retrieva de 9 docs sintéticos do "Banco Seguro". Vamos ingerir o dataset público `Itau-Unibanco/FAQ_BACEN` no Qdrant para o entrevistador ver respostas baseadas em material real do Itaú.

Switch via env var `LLM_PROVIDER` (`anthropic` default, `mock` desativa só o judge).

## Assunções

- Sonnet 4.6 continua online para `generate` (chatbot) — `ANTHROPIC_API_KEY` ainda necessário. Se a intenção era *fully offline*, abrir nova issue (não é o escopo escolhido na pergunta).
- O dataset `Itau-Unibanco/FAQ_BACEN` continua acessível no HF Hub sem auth (verificar no passo 4).
- Vamos manter o nome de variável `LLM_PROVIDER` para reuso futuro (ex: AWS Bedrock no Extras), mas no MVP afeta apenas o componente Compliance.

## Mudanças

### 1. Portar detectores rule-based

Criar `guardrails/detectors/` espelhando estrutura do projeto antigo. Cada detector é função pura `detect(text) -> DetectionResult{detected, confidence, matched_patterns, rule_id}`.

Arquivos novos:
- `guardrails/detectors/__init__.py`
- `guardrails/detectors/base.py` — dataclass `DetectionResult` + ABC `BaseDetector` (mínimo, sem joblib/sklearn deps opcionais do original)
- `guardrails/detectors/financial_advice.py` — 6 regras regex PT-BR (promessa rentab., minimização risco, recomendação direta, alocação indevida, comparação absoluta, urgência)
- `guardrails/detectors/fraud.py` — 4 regras (credenciais, personificação, doc falso, bypass auth)
- `guardrails/detectors/data_leak.py` — regex (api_key/token/jwt/url_interna) + 11 sensitive words co-ocorrendo com verbos de exposição
- `guardrails/detectors/out_of_scope.py` — versão **simplificada keyword-only** (allowlist bancária PT-BR de ~40 termos: pix, cdb, lci, conta, cartão, empréstimo, etc.). Pular embedding similarity para evitar +120MB de dependência e tempo de port. Documentar trade-off em `LIMITATIONS.md`.

**Não copiar do antigo**: `pii.py`, `prompt_injection.py`, `toxicity.py` — já cobertos pelos validators atuais (`pii_input`, `pii_output`, `jailbreak`, `toxic`).

### 2. Novo validator: `RuleBasedComplianceValidator`

Arquivo novo: `guardrails/validators/compliance_rules.py`

- Mesma interface pública do `ComplianceValidator` (`run(text) -> ValidatorResult`).
- Internamente chama os 4 detectores em sequência (curto-circuito na primeira regra que dispara).
- Mapeia detector→rubrica R1-R5 (para preservar `rule_violated` no `block_details` e nos logs JSON):
  - `financial_advice.promessa_rentabilidade` / `minimizacao_risco` → **R1**
  - `financial_advice.recomendacao_direta` / `alocacao_indevida` / `comparacao_absoluta` / `urgencia` → **R2**
  - `fraud.*` → **R3** (ação fraudulenta/não-executável)
  - `data_leak.*` → **R4** (vazamento de instruções/credenciais)
  - `out_of_scope.detected` → **R5** (fora do escopo)
- Preencher `reasoning` com `matched_patterns` para a UI Streamlit continuar mostrando diagnóstico.

### 3. Switch `LLM_PROVIDER`

Arquivo modificado: `guardrails/api/app.py` (factory `_create_components`, linhas ~27-89).

```python
provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
if provider == "mock":
    compliance = RuleBasedComplianceValidator()
else:
    compliance = ComplianceValidator(model=..., api_key=...)
```

- **Não tocar** no `AnthropicProvider` (chatbot Sonnet continua).
- Adicionar variável em `docker-compose.yml` (default vazio → `anthropic`).
- Documentar em `README.md` (seção Demo).

### 4. Ingestão Itaú FAQ_BACEN no Qdrant

Arquivo novo: `scripts/ingest_itau_faq.py` baseado em `scripts/ingest_banking_kb.py`.

- Carrega `Itau-Unibanco/FAQ_BACEN` via `datasets.load_dataset` (já é dep transitiva via sentence-transformers).
- Cada item do dataset (pergunta+resposta) vira um chunk; metadata `source="itau_faq_bacen"`.
- Embed com `intfloat/multilingual-e5-small` (mesmo modelo do RAG atual — sem mudar embedding stack).
- Cria/popula coleção `itau_faq` no Qdrant (separada de `banking_kb` para permitir A/B se necessário).

Arquivo modificado: `config.yaml` — campo `qdrant.collection: itau_faq` (ou adicionar `qdrant.collections.primary`).

Arquivo modificado: `guardrails/pipeline/nodes.py` `retrieve()` — apenas se nome de coleção for hard-coded; caso contrário só muda via config.

### 5. Documentação

Arquivos modificados:
- `LIMITATIONS.md` — adicionar seção "Rule-Based Compliance (modo `LLM_PROVIDER=mock`)" listando: falha em paráfrase, falha em negação implícita, `out_of_scope` keyword-only é menos preciso que embedding similarity, sem detecção de promessa via tom (só via léxico).
- `README.md` — seção "Demo modes": `anthropic` (default, com judge LLM) vs `mock` (rule-based, ideal para demo offline-safe).
- `CLAUDE.md` — adicionar linha na tabela de Decisões: "Modo dual de Compliance (LLM judge vs rule-based) via `LLM_PROVIDER`, decidido 2026-05-29 para de-risk demo Itaú".
- Criar/atualizar ADR curto em `.claude/agents/ADRs/` (se diretório existir) sobre o trade-off.

### 6. Testes

Arquivos novos:
- `tests/test_detectors_financial_advice.py`, `tests/test_detectors_fraud.py`, `tests/test_detectors_data_leak.py`, `tests/test_detectors_out_of_scope.py` — fixtures hand-crafted, **declarar loop fechado** em cada arquivo (building-rigorously.md §1).
- `tests/test_compliance_rules_integration.py` — rodar as mesmas fixtures de `tests/test_compliance.py` (Beat 4 da demo) contra `RuleBasedComplianceValidator` e verificar mapeamento R1-R5.

**Esperar regressão**: building-rigorously.md §3 — se tudo passar de primeira contra a rubrica do LLM judge, suspeitar. Documentar bypasses conhecidos como `xfail`.

## Critical files

- `guardrails/api/app.py` (switch)
- `guardrails/validators/compliance_rules.py` (novo)
- `guardrails/detectors/{financial_advice,fraud,data_leak,out_of_scope,base}.py` (novos)
- `scripts/ingest_itau_faq.py` (novo)
- `config.yaml`, `docker-compose.yml`, `LIMITATIONS.md`, `README.md`, `CLAUDE.md`
- Fonte de referência (read-only): https://github.com/germanojorge/guardrail-bancario/tree/master/src/guardrail/detectors

## Verificação end-to-end

1. **Detectores unitários**: `pytest tests/test_detectors_*.py -v` — todas verdes, com pelo menos 1 `xfail` por detector documentando bypass conhecido.
2. **Demo mock**:
   ```bash
   LLM_PROVIDER=mock docker compose up
   ```
   - Beat 1 (cartão Gold) → passa, retrieva chunk Itaú real.
   - Beat 4 (recomendação financeira indevida) → bloqueio com `rule_violated: R2` vindo de `financial_advice.recomendacao_direta`.
   - `docker logs api | jq 'select(.event=="block")'` mostra evento com `category=compliance`, `validator=rule_based`.
3. **Demo LLM judge** (regression):
   ```bash
   docker compose up
   ```
   - Mesmo Beat 4 → bloqueio via Haiku judge, `rule_violated: R2` (mesmo mapping).
4. **RAG Itaú**: query no Streamlit "Como funciona o Pix" — top chunk deve ter `source: itau_faq_bacen`.
5. **Adversarial**: rodar `tests/adversarial_smoke.py` em ambos os modos; aceitar diferença de cobertura entre LLM judge e rule-based (documentar em LIMITATIONS).

## Estimativa de tempo

- Portar 4 detectores + base: **1h** (regex copy-paste + simplificar out_of_scope).
- `RuleBasedComplianceValidator` + mapping R1-R5: **30min**.
- Switch `LLM_PROVIDER` + docker-compose: **20min**.
- Ingest Itaú FAQ + config: **45min** (download dataset + embed + verificar Qdrant).
- Testes + LIMITATIONS + README: **45min**.
- **Total**: ~3h15min. Cabe na janela pré-entrevista.
