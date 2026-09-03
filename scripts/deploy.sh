#!/usr/bin/env bash
# Deploy the dev environment and wire local config from Terraform outputs
# (SPEC.md §12, DEPLOY.md §1/§2/§5/§6). Runs BILLABLE AWS commands.
#
#   scripts/deploy.sh                 # terraform plan only (safe default)
#   scripts/deploy.sh --apply         # terraform apply, then write .env + harness_config.yaml
#
# Prereqs: aws creds (aws sso login), terraform, docker (for the ARM64 runtime image).
set -euo pipefail
cd "$(dirname "$0")/.."

TF="terraform -chdir=infra/envs/dev"
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

$TF init -input=false

if [[ "$APPLY" -eq 0 ]]; then
  echo "[deploy] plan only — re-run with --apply to create resources"
  exec $TF plan
fi

echo "[deploy] applying (billable) ..."
$TF apply -auto-approve

echo "[deploy] writing .env from outputs"
$TF output -json > .deploy-outputs.json
trap 'rm -f .deploy-outputs.json' EXIT
python3 <<'PY'
import json, pathlib
o = json.loads(pathlib.Path(".deploy-outputs.json").read_text())
def v(k):
    return o.get(k, {}).get("value") or ""
lines = {
    "AWS_REGION": v("aws_region") or "us-east-1",
    "AURORA_CLUSTER_ARN": v("aurora_cluster_arn"),
    "AURORA_SECRET_ARN": v("aurora_secret_arn"),
    "AURORA_DATABASE_NAME": v("aurora_database_name"),
    "KNOWLEDGE_BASE_ID": v("knowledge_base_id"),
    "BEDROCK_GUARDRAIL_ID": v("bedrock_guardrail_id"),
    "BEDROCK_GUARDRAIL_VERSION": v("bedrock_guardrail_version"),
    "AGENTCORE_RUNTIME_ARN": v("agentcore_runtime_arn"),
}
env = pathlib.Path(".env")
existing = {}
if env.exists():
    for ln in env.read_text().splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            k, _, val = ln.partition("=")
            existing[k.strip()] = val
existing.update({k: val for k, val in lines.items() if val})
env.write_text("\n".join(f"{k}={val}" for k, val in existing.items()) + "\n")
print("  wrote", ", ".join(k for k, val in lines.items() if val))
PY

echo "[deploy] rendering agent/harness_config.yaml"
python3 <<'PY'
import json, pathlib
o = json.loads(pathlib.Path(".deploy-outputs.json").read_text())
def v(k): return o.get(k, {}).get("value") or ""
cfg = pathlib.Path("agent/harness_config.yaml").read_text()
repl = {
    'id: ""': 'id: ""  # set your generation model id',
    'arn: ""                      # aws_bedrockagentcore_memory output': f'arn: "{v("agentcore_memory_id")}"',
    'id: ""                       # bedrock guardrail id': f'id: "{v("bedrock_guardrail_id")}"',
    'version: ""': f'version: "{v("bedrock_guardrail_version")}"',
}
for a, b in repl.items():
    cfg = cfg.replace(a, b, 1)
pathlib.Path("agent/harness_config.yaml").write_text(cfg)
print("  updated memory/guardrail refs")
PY

echo "[deploy] done. Smoke test: agentcore invoke (see DEPLOY.md §6)"
