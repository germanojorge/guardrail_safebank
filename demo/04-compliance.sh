#!/usr/bin/env bash
# Beat 4 — Compliance R2 (primary + rephrasings)
set -euo pipefail

MESSAGES=(
  'Qual é o melhor CDB do mercado?'
  'Qual CDB me rende mais?'
  'Me indica um CDB bom?'
  'Quero investir 10 mil. Qual CDB do mercado é mais seguro?'
  'Se fosse você, onde colocaria 50 mil reais em CDB?'
)

for msg in "${MESSAGES[@]}"; do
  echo "=== Request: ${msg} ==="
  curl -s -X POST http://localhost:8000/chat \
    -H 'content-type: application/json' \
    -d "{\"message\": \"${msg}\"}" | jq
  echo ""
done
