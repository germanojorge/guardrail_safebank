🏠 [Home](./README_FOR_HUMANS.md) · [Getting Started](./GETTING_STARTED.md) · [Architecture](./ARCHITECTURE.md) · [Tech](./TECH_STACK.md) · [Integrations](./INTEGRATIONS.md) · [Repo Map](./MAP/repo_map.md) · [Links](./LINKS.md)

---

# Starter Tasks

> Coisas pequenas pra ganhar confiança no repo. Pega **uma** e fecha — vitórias pequenas batem planos grandes.

## Warm-up (≈ 15 min)

- Subir a stack com `docker compose up -d` + `docker compose run --rm ingest` e ver a UI Streamlit em http://localhost:8501.
- Rodar os 4 beats da demo com `curl` (Beat 1–4 no README) e ler os `diagnostics` no JSON de resposta.
- Rodar `uv run pytest -m "not slow and not network" -q` e ver o output verde.
- Ler `CLAUDE.md` → seção "Decisões Já Tomadas" pra absorver o contexto rápido.
- Ler `LIMITATIONS.md` — onde o sistema *sabe* que falha (mais valioso que o README).

## Primeira mudança real (≈ 1–2 h)

- **Adicionar uma regra ao detector de fraude** (`guardrails/detectors/fraud.py`) e cobrir com um teste em `tests/unit/test_detectors_fraud.py`.
- **Adicionar um doc PT-BR ao `data/banking_kb/`** sobre um produto bancário novo, re-rodar `ingest`, e validar que o RAG recupera no Beat 1.
- **Reduzir o `threshold` do jailbreak no `config.yaml`** e medir o impacto no `tests/adversarial/test_jailbreak_pipeline.py` (block rate sobe? falsos positivos sobem?).
- **Trocar a mensagem de bloqueio padrão** (procura por "<mensagem padronizada>" ou similar em `guardrails/pipeline/nodes.py`) pra algo mais útil ao cliente do banco.
- **Acrescentar um teste de fail-closed** em `tests/api/test_fail_closed.py` pra um cenário novo (ex: Qdrant fora do ar).

## Aprender o código fazendo

- **Traçar uma requisição inteira**: começa em `guardrails/api/app.py` (`POST /chat`), segue pra `guardrails/pipeline/graph.py` (`build_graph`), depois `nodes.py`. Escreve um comentário ou doc explicando o caminho.
- **Comparar `ComplianceValidator` (Haiku) com `RuleBasedComplianceValidator`** (`guardrails/validators/compliance*.py`): o que perdeu e o que ganhou no modo mock? Documenta em `.buddy/NOTES/`.
- **Adicionar uma 5ª camada ao jailbreak validator** (ex: classifier zero-shot) e medir contribuição com `scripts/measure_jailbreak_layers.py`.
- **Mapear quais ADRs ficaram desatualizados** (ex: ADR 005 sobre Presidio — o código já usa Presidio NER opcional). Abre PR atualizando o ADR.

## TODOs / FIXMEs no código

> Procura com `grep -RIn "TODO\|FIXME\|XXX" guardrails/ tests/ scripts/`. Costuma valer ouro pra contribuição pequena.

## Dicas

- **Pergunta cedo.** Se uma task leva >30 min só pra entender, isso já é feedback útil.
- **PRs pequenos vencem.** Uma linha hoje > refactor enorme mês que vem.
- **Atualiza o Buddy.** Aprendeu algo? Joga em `.buddy/*.md` pro próximo recém-chegado.
