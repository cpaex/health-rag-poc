#!/usr/bin/env bash
# Deploy the dev environment (SPEC.md §12). Fleshed out across Phases 1, 2, 6.
# Runs billable AWS commands — do not invoke without explicit confirmation.
set -euo pipefail

echo "[deploy] TODO Phase 1: terraform -chdir=infra/envs/dev init/plan/apply"
echo "[deploy] TODO Phase 2: trigger KB ingestion / smoke test"
echo "[deploy] TODO Phase 6: package ARM64 runtime, agentcore deploy, write agent/harness_config.yaml"
exit 0
