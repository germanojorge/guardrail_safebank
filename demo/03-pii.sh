#!/usr/bin/env bash
# Beat 3 — PII CPF
set -euo pipefail
curl -s -X POST http://localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Meu CPF é 123.456.789-09"}' | jq
