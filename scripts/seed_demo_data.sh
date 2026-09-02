#!/usr/bin/env bash
# Run the full ingestion pipeline end-to-end against the synthetic seed data
# (SPEC.md §6 step 6). Live AWS: this calls Comprehend Medical, Bedrock (Titan),
# and the Aurora RDS Data API. See DEPLOY.md §3.
#
#   scripts/seed_demo_data.sh              # real run (needs AWS creds + deployed dev env)
#   scripts/seed_demo_data.sh --dry-run    # no AWS, no DB — wiring check only
set -euo pipefail

cd "$(dirname "$0")/.."

DRY_RUN=""
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN="--dry-run"

if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi

if [[ -z "$DRY_RUN" ]]; then
  : "${AURORA_CLUSTER_ARN:?set in .env (DEPLOY.md §1)}"
  : "${AURORA_SECRET_ARN:?set in .env (DEPLOY.md §1)}"
  : "${AWS_REGION:=us-east-1}"

  RAW_BUCKET="$(terraform -chdir=infra/envs/dev output -raw raw_notes_bucket 2>/dev/null || true)"
  SEED_BUCKET="$(terraform -chdir=infra/envs/dev output -raw seed_fhir_bucket 2>/dev/null || true)"
  if [[ -n "$RAW_BUCKET" ]]; then
    echo "[seed] uploading notes -> s3://$RAW_BUCKET/"
    aws s3 sync ingestion/seed_data/notes "s3://$RAW_BUCKET/notes" --exclude "manifest.jsonl"
  fi
  if [[ -n "$SEED_BUCKET" ]]; then
    echo "[seed] uploading FHIR -> s3://$SEED_BUCKET/"
    aws s3 sync ingestion/seed_data/fhir "s3://$SEED_BUCKET/fhir"
  fi
fi

echo "[seed] running ingestion pipeline ${DRY_RUN:-(live)}"
python -m ingestion.pipeline $DRY_RUN

if [[ -z "$DRY_RUN" && -n "${KNOWLEDGE_BASE_ID:-}" ]]; then
  echo "[seed] KB Retrieve smoke test"
  python scripts/kb_smoke_test.py --kb-id "$KNOWLEDGE_BASE_ID" --patient-scope patient-001
fi

echo "[seed] done"
