#!/usr/bin/env bash
# Merge current Terraform outputs from infra/envs/dev into the repo-root .env
# (DEPLOY.md). Safe to run repeatedly after each staged `terraform apply` — it
# only adds/updates keys that have a non-empty value and leaves the rest alone.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="$(terraform -chdir=infra/envs/dev output -json)"

MAP='
aws_region                AWS_REGION
aurora_cluster_arn        AURORA_CLUSTER_ARN
aurora_secret_arn         AURORA_SECRET_ARN
aurora_database_name      AURORA_DATABASE_NAME
raw_notes_bucket          RAW_NOTES_BUCKET
seed_fhir_bucket          SEED_FHIR_BUCKET
knowledge_base_id         KNOWLEDGE_BASE_ID
bedrock_guardrail_id      BEDROCK_GUARDRAIL_ID
bedrock_guardrail_version BEDROCK_GUARDRAIL_VERSION
agentcore_runtime_arn     AGENTCORE_RUNTIME_ARN
'

OUT="$OUT" MAP="$MAP" python3 <<'PY'
import json, os, pathlib
o = json.loads(os.environ["OUT"])
env = pathlib.Path(".env")
kv = {}
if env.exists():
    for ln in env.read_text().splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, _, v = ln.partition("=")
            kv[k.strip()] = v
added = []
for line in os.environ["MAP"].split("\n"):
    line = line.split()
    if len(line) != 2:
        continue
    tf_key, env_key = line
    val = o.get(tf_key, {}).get("value")
    if val:
        kv[env_key] = str(val)
        added.append(env_key)
env.write_text("\n".join(f"{k}={v}" for k, v in kv.items()) + "\n")
print("synced:", ", ".join(added) or "(nothing yet)")
PY
