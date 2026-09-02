# DEPLOY.md — Clinical Agentic RAG deployment runbook

Stand the whole system up from a clean AWS account. **This is the only document
that runs `terraform apply` or any billable AWS command.** The repo build
(SPEC.md phases) produces local files only; everything live happens here.

Run the sections in order. Each step gives the exact command, the expected
signal, and an "if this fails" pointer. Sections marked _(pending Phase N)_ are
filled in as that phase is built.

---

## 0. Prerequisites

| Need | How |
|---|---|
| AWS credentials | `aws sso login --profile DevOps-905418344519` (account `905418344519`, `us-east-1`). Verify: `AWS_PROFILE=DevOps-905418344519 aws sts get-caller-identity`. |
| Region | `export AWS_REGION=us-east-1 AWS_PROFILE=DevOps-905418344519` |
| Terraform / tflint | `terraform -version` (≥ 1.6; built with 1.16.0), `tflint --version` (built with 0.64.0) |
| Python | 3.11+; `pip install -e ".[dev,ingestion,evals,mockfhir,ui]"` |
| Bedrock model access | In the Bedrock console → *Model access*, request/enable: **Amazon Titan Text Embeddings V2** (`amazon.titan-embed-text-v2:0`), **Cohere Rerank 3.5** (`cohere.rerank-v3-5:0`), and the generation model used by the agent. Access is per-account, per-region, and not managed by Terraform. |
| Account-level toggles | CloudWatch Transaction Search / X-Ray trace ingestion for AgentCore Observability — see §6 _(pending Phase 6)_. |

**Estimated standing cost of the fully-deployed dev stack:** Aurora Serverless v2
at the 0.5-ACU floor dominates (~$45–55/mo running 24/7); VPC/subnets/SG/S3/IAM/KB
metadata are ~$0 at rest; Bedrock/Comprehend Medical are per-call. Apply + destroy
same-day ≈ a few dollars. Switch `data_aurora` `min_capacity` to `0` for
scale-to-zero (trade-off: cold-start latency on first query after idle).

---

## 1. Foundation — network + Aurora + S3 + IAM

```bash
cd infra/envs/dev
terraform init
terraform plan            # review: VPC, 2 subnets, DB subnet group, SG,
                          # aurora-postgresql 16.8 Serverless v2 cluster + 1 instance,
                          # RDS-managed master secret, 2 S3 buckets, ingestion IAM role
terraform apply           # ~10–15 min (Aurora cluster creation dominates)
```

**Post-apply:**

```bash
# Capture outputs into repo .env
terraform output -json | python3 - <<'PY'
import json,sys
o=json.load(sys.stdin)
m={
 "AWS_REGION":o["aws_region"]["value"],
 "AURORA_CLUSTER_ARN":o["aurora_cluster_arn"]["value"],
 "AURORA_SECRET_ARN":o["aurora_secret_arn"]["value"],
}
open("../../.env","a").write("\n".join(f"{k}={v}" for k,v in m.items())+"\n")
print("wrote", *m)
PY
```

The §4 schema migration (`infra/modules/data_aurora/sql/001_init.sql`) runs
automatically at apply time via the `null_resource.schema_bootstrap` local-exec
(`scripts/apply_sql.py` over the RDS Data API). It is idempotent.

**Verify:**

```bash
python3 scripts/apply_sql.py \
  --resource-arn "$AURORA_CLUSTER_ARN" --secret-arn "$AURORA_SECRET_ARN" \
  --database clinical_rag --file /dev/stdin <<'SQL'
SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm');
SELECT table_schema||'.'||table_name FROM information_schema.tables
 WHERE table_name IN ('bedrock_kb','ontology_index');
SQL
```

Expected: `vector` and `pg_trgm` present; `bedrock_integration.bedrock_kb` and
`ontology_index` listed.

**If this fails:** `DatabaseResumingException` → re-run, the cluster is waking
(script retries 10×). Preflight/permission errors → confirm the caller can reach
`rds-data` and read the secret; check the cluster has `enable_http_endpoint = true`.

---

## 2. Knowledge Base

```bash
cd infra/envs/dev
terraform plan            # review: aws_bedrockagent_knowledge_base (VECTOR + RDS
                          # storage, field_mapping -> §4 columns), aws_bedrockagent_data_source
                          # (S3, chunking NONE), KB service role
terraform apply
terraform output knowledge_base_id      # -> append KNOWLEDGE_BASE_ID=... to ../../.env
```

Bedrock runs a create-time preflight against the Aurora table; §1 must have
applied the schema first (the module's `depends_on = [module.data_aurora]`
enforces ordering).

**Verify (expect zero results until §3 loads data):**

```bash
python scripts/kb_smoke_test.py --kb-id "$KNOWLEDGE_BASE_ID"
```

Expected: runs without error, `results : 0`. **Hybrid search** is exercised here
via `overrideSearchType=HYBRID` in the script — there is no Terraform toggle for
it (dense = pgvector HNSW, sparse = the §4 GIN full-text index).

**If this fails:** `ValidationException` about columns → the `field_mapping` in
`infra/modules/knowledge_base/main.tf` must match the actual `bedrock_kb`
columns; re-check against the §4 migration. Role errors → the KB role needs
`rds-data:*`, `secretsmanager:GetSecretValue`, and `bedrock:InvokeModel` on the
Titan ARN.

---

## 3. Ingestion — seed data + pipeline

Requires §1 (`.env` has `AURORA_CLUSTER_ARN`, `AURORA_SECRET_ARN`) and §2
(`KNOWLEDGE_BASE_ID`) done. Uses Comprehend Medical + Bedrock (Titan) + the RDS
Data API — all billable but small (10 synthetic notes).

**Optional pre-check (no AWS, no DB):**

```bash
scripts/seed_demo_data.sh --dry-run
# expect: {"notes": 10, "chunks": 38, "kb_rows": 38, ...}
```

**Live run:**

```bash
# assumes .env is populated from §1 / §2
scripts/seed_demo_data.sh
```

This: uploads `ingestion/seed_data/notes` + `fhir` to the S3 buckets; runs
`python -m ingestion.pipeline` (per note: `DetectPHI` → redact → section-aware
chunk → Titan V2 embed → insert `bedrock_integration.bedrock_kb` → `Infer*`
ontology link → insert `ontology_index`); then runs the KB smoke test scoped to
`patient-001`.

**Verify:**

```bash
python3 scripts/apply_sql.py --resource-arn "$AURORA_CLUSTER_ARN" \
  --secret-arn "$AURORA_SECRET_ARN" --database clinical_rag --file /dev/stdin <<'SQL'
SELECT count(*) FROM bedrock_integration.bedrock_kb;
SELECT count(*) FROM ontology_index;
SELECT count(DISTINCT custom_metadata->>'patient_scope') FROM bedrock_integration.bedrock_kb;
SQL

python scripts/kb_smoke_test.py --kb-id "$KNOWLEDGE_BASE_ID" \
  --query "reaction to the dye study" --patient-scope patient-001
```

Expected: `bedrock_kb` ~38 rows, `ontology_index` > 0, 3 distinct patient scopes;
the smoke test returns non-empty results **all scoped to `patient-001`** (exit 0;
it fails loudly if any row is out of scope), including `note-001` / `note-003` /
`note-010` for the contrast-dye query.

**If this fails:** `RETURNING id` empty → the KB table isn't the §4 schema, re-run
§1 verify. `AccessDenied` on `comprehendmedical:*` → the caller/role needs the
Phase 1 `ingestion` policy. Embedding dimension mismatch → confirm
`amazon.titan-embed-text-v2:0` and `dimensions=1024` vs `vector(1024)`.

---

## 4. Agent — local mode

Requires §1–§3. Uses a Bedrock generation model (agent) + Cohere Rerank 3.5 +
Comprehend-less retrieval tools — all billable per call.

**Bedrock model access:** confirm the generation model the agent uses is enabled
(§0) and set its id in `agent/harness_config.yaml` / wherever `_build_model`
reads it.

**Start the mock FHIR endpoint** (separate shell):

```bash
pip install -e ".[mockfhir]"
scripts/run_mock_fhir.sh 8000        # -> http://127.0.0.1:8000  (GET /healthz)
```

**`.env`** must now have `KNOWLEDGE_BASE_ID`, `AURORA_CLUSTER_ARN`,
`AURORA_SECRET_ARN`, `AWS_REGION`, `MOCK_FHIR_ENDPOINT_URL=http://127.0.0.1:8000`,
`RERANK_MODEL_ARN`, `AGENT_MODE=local`.

**Run the multi-step demo question:**

```bash
python - <<'PY'
from agent.supervisor import answer
r = answer("Has this patient ever reacted to imaging contrast, and what should we do next time?",
           "patient-001", mode="local")
print(r["answer"])
PY
```

**Verify:**
- The answer cites `note-001` / `note-003` / `note-010` (the contrast-dye thread).
- Enable step logging (or call `agent.retrieval_strategy.hybrid_multistep`
  directly with the bound tools) and confirm the sequence
  `ontology_lookup → kb_hybrid_retrieve → kb_hybrid_retrieve (broadened) →
  rerank` — i.e. it resolved the term, noticed the thin first pass, broadened,
  and reranked.
- A question about `patient-002` returns nothing from `patient-001`'s notes.

**If this fails:** `AccessDeniedException` invoking the model → model access not
enabled in this region. Empty retrieval → re-run §3 verify. `httpx.ConnectError`
→ the mock FHIR server isn't running / `MOCK_FHIR_ENDPOINT_URL` wrong.

---

## 5. Guardrails & Identity   _(pending Phase 5)_

`terraform apply` the `guardrails` module; append `BEDROCK_GUARDRAIL_ID` /
`BEDROCK_GUARDRAIL_VERSION` to `.env`; run the live cross-patient-scope
prompt-injection test and confirm the block happens before the model call.

---

## 6. AgentCore deployment   _(pending Phase 6)_

Any one-time account-level Observability enable (Transaction Search / X-Ray trace
ingestion); ARM64 build & package of the runtime; `terraform apply` the
`agentcore` + `observability` modules; invoke the deployed runtime
(`agentcore invoke` / `InvokeAgentRuntime`); `AGENT_MODE=agentcore` smoke test.

---

## 7. Evaluation   _(pending Phase 7)_

Live RAGAS run against the deployed stack to confirm the faithfulness threshold
gate fires; `python evals/run_bedrock_evaluations.py` to launch a managed job and
print its job ID; where to read the results.

---

## 8. UI   _(pending Phase 8)_

`streamlit run ui/streamlit_app.py` in both `local` and `agentcore` modes;
end-to-end answer with visible citations.

---

## 9. Teardown

Destroy in reverse dependency order. S3 buckets and any KB-ingested data must be
emptied first.

```bash
# empty buckets (versioned) before destroy
for b in $(cd infra/envs/dev && terraform output -raw raw_notes_bucket) \
         $(cd infra/envs/dev && terraform output -raw seed_fhir_bucket); do
  aws s3api delete-objects --bucket "$b" \
    --delete "$(aws s3api list-object-versions --bucket "$b" \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null || true
done

cd infra/envs/dev && terraform destroy
```

**Not destroyed by `terraform destroy`:** Bedrock model access grants,
account-level CloudWatch Transaction Search enablement, anything created by hand
in a `DEPLOY.md` step, and this file. **Residual-cost checklist:** confirm the
Aurora cluster, its RDS-managed secret, and both S3 buckets are gone; check for
leftover CloudWatch log groups.
