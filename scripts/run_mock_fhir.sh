#!/usr/bin/env bash
# Start the mocked FHIR endpoint for local dev (SPEC.md §2 non-goal).
#   pip install -e ".[mockfhir]"
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8000}"
exec python -m uvicorn mocks.fhir_server:app --host 127.0.0.1 --port "$PORT"
