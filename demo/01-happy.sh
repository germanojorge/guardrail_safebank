#!/usr/bin/env bash
# Beat 1 — Happy Path (Cartão Gold)
set -euo pipefail
curl -s -X POST http://localhost:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Qual a diferença entre o PIX e o DOC?"}' | jq
