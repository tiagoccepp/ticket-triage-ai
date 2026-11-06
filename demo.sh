#!/usr/bin/env bash
# One-command local demo: boots the API on port 8002 (system python3, keyless).
# Usage: ./demo.sh
set -euo pipefail
cd "$(dirname "$0")"
export LLM_PROVIDER="${LLM_PROVIDER:-mock}"
echo "Booting ticket-triage-ai on http://127.0.0.1:8002 (LLM_PROVIDER=$LLM_PROVIDER) ..."
echo "Endpoints:"
echo "  GET  /health"
echo "  POST /tickets/submit   {\"title\": ..., \"body\": ..., \"customer_id\": ...}"
echo "  GET  /review-queue"
echo "  GET  /metrics"
echo "  GET  /tickets/{id}"
echo "  GET  /ui            (demo web UI — open in browser)"
echo ""
echo "Full request/response transcript: demo/transcript.md"
exec python3 -m uvicorn src.api:app --port 8002
