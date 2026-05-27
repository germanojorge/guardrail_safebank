# Demo & Rehearsal — Guardrail Bancário

> Roteiro cronometrado de 8 minutos para a entrevista técnica.

---

## Pré-requisitos

- Docker Engine ≥ 24 com `docker compose` v2
- Anthropic API key (`export ANTHROPIC_API_KEY=sk-ant-...`)
- ~2.5 GB de RAM alocada para Docker (models ~1.5 GB)
- `jq` instalado (opcional, para colorir JSON nos shells)
- `curl` e `bash` (para os sidecars `.sh`)

---

## Roteiro de 8 Minutos

| Minuto | Beat | Ação | Fala Sugerida | Tempo Alvo |
|---|---|---|---|---|
| 0:00-0:30 | Setup | `docker compose down -v && docker compose up -d` + `docker compose run --rm ingest` | "Vou subir a stack do zero em uma máquina limpa." | 30s |
| 0:30-2:00 | Beat 1 — Happy Path | `demo/01-happy.sh` ou UI Streamlit | "Cliente pergunta sobre o cartão Gold. O pipeline passa, RAG recupera chunks, resposta natural." | 90s |
| 2:00-3:30 | Beat 2 — Jailbreak DAN | `demo/02-jailbreak.sh` | "Ataque de prompt injection. A defesa em camadas — substring fast-path + DeBERTa — bloqueia antes do LLM." | 90s |
| 3:30-5:00 | Beat 3 — PII CPF | `demo/03-pii.sh` | "O usuário manda CPF. O guardrail de input detecta via regex PT-BR e bloqueia. Dado sensível nunca sai do sistema." | 90s |
| 5:00-6:30 | Beat 4 — Compliance R2 (Killer) | `demo/04-compliance.sh` | "A pergunta é inocente: 'Qual o melhor CDB?' O LLM responde algo plausível. Mas o Judge Haiku captura a violação sutil de compliance — isso só um LLM consegue." | 90s |
| 6:30-7:30 | Logs + CI | `docker logs api \| jq` + badge CI | "Cada evento é JSON estruturado. Veja o breakdown de latência por stage. E o CI roda testes adversariais a cada push." | 60s |
| 7:30-8:00 | Closing | Slide de arquitetura | "Arquitetura de proxy com LangGraph, validators custom em Python puro, e abstração de provider pronta para AWS Bedrock." | 30s |

**Total alvo: 8 minutos.**

---

## Fallbacks

### Se o Beat 4 falhar (Compliance Judge)

O Compliance Judge depende da API da Anthropic. Se houver instabilidade:

1. **Use Plan B (R3)**: rode `python demo/scripts/test_beat4.py --plan-b`
   - R3 é mais fácil de bloquear (ação não-executável) e não depende de nuance semântica.
2. **Mostre o vídeo de backup**: grave previamente com `python demo/scripts/auto_demo.py`.
3. **Mostre os logs JSON** de uma execução anterior salva.

### Se o Docker estiver lento

- Use os arquivos `.sh` em vez da UI Streamlit (menos overhead).
- Ou execute `python demo/scripts/auto_demo.py` que já faz os POSTs via `httpx` e mostra os diagnostics no terminal.

### Se a internet cair

- Mostre o **vídeo de backup gravado** (auto-demo robot com `--dry-run` não precisa de internet, mas não mostra respostas reais).
- Abra o `.http` files no VSCode para mostrar que os requests estão prontos.

### Se o ingest falhar

- Rode `docker compose run --rm ingest` novamente. O script é idempotente (sobrescreve a collection).

---

## Scripts de Rehearsal

| Script | Propósito | Comando típico |
|---|---|---|
| `demo/scripts/auto_demo.py` | Robot que percorre os 4 beats com pausas de 2s, ideal para gravar vídeo de backup. | `python demo/scripts/auto_demo.py` |
| `demo/scripts/consistency_test.py` | Roda os 4 beats 3x em stack limpa, verifica flakiness e limite de 8min. | `python demo/scripts/consistency_test.py --rounds 3` |
| `demo/scripts/test_beat4.py` | Testa 6 rephrasings do Beat 4 e exige ≥80% de bloqueio com `rule_violated=R2`. | `python demo/scripts/test_beat4.py` |
| `demo/scripts/timer.py` | Utilitários compartilhados (`Timer`, `StageTimer`, `assert_under_limit`). | Importado pelos scripts acima. |

---

## Request Files

Arquivos `.http` compatíveis com VSCode REST Client / IntelliJ HTTP Client:

- `demo/01-happy.http` — Beat 1 (cartão Gold)
- `demo/02-jailbreak.http` — Beat 2 (DAN)
- `demo/03-pii.http` — Beat 3 (CPF)
- `demo/04-compliance.http` — Beat 4 + 4 rephrasings

Sidecars `.sh` com `curl` + `jq` para terminal:

- `demo/01-happy.sh`
- `demo/02-jailbreak.sh`
- `demo/03-pii.sh`
- `demo/04-compliance.sh`

---

*Gerado pelo plano SCRUM-16. Valide sempre com `bash -n demo/*.sh` e `python demo/scripts/auto_demo.py --dry-run` antes da entrevista.*
