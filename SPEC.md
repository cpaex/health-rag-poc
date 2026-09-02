# SPEC.md — Clinical Agentic RAG Starter Repository

This is a build specification for **Claude Code**. It describes a repository to scaffold from scratch: an agentic, hybrid-retrieval RAG platform over clinical notes, built on Amazon Bedrock AgentCore. Follow the phases in order; treat each phase's "Definition of Done" as a gate before moving to the next. Ask before running anything that touches real AWS billing (Phase 1 `terraform apply` onward).

> Companion reading (not required to build, but explains the *why* behind these choices): the architecture document and concept glossary this spec was derived from. If they're present in `docs/`, read them before Phase 1.

---

## 1. Decisions already made — do not re-litigate these

| Decision | Choice | Why |
|---|---|---|
| Vector store | **Bedrock Knowledge Base on Amazon Aurora PostgreSQL (pgvector)** | Native hybrid search (dense + full-text) GA since April 2025; co-locates relational metadata with vectors |
| De-identification / ontology linking | **Real Amazon Comprehend Medical pipeline code**, seeded with **synthetic FHIR data** | Ships production-real logic without touching real PHI during development |
| IaC | **Terraform** | Bedrock AgentCore resources (`aws_bedrockagentcore_agent_runtime`, `_gateway`, `_memory`, etc.) are supported in `hashicorp/aws` provider v6.51+ |
| Agent framework | Strands Agents, "Agent-as-Tools" supervisor pattern | Matches `aws-samples/sample-bedrock-agentcore-healthcare-s3vectors`, native AgentCore integration |
| Embedding model | Amazon Titan Text Embeddings V2 | Bedrock-native, no extra vendor subscription |
| Reranker | Cohere Rerank 3.5 via Bedrock Rerank API | Best precision/latency trade-off currently available on Bedrock |
| Guardrails | Amazon Bedrock Guardrails (sensitive-info filters + denied topics + prompt-attack protection) | Not present in the reference repo — this project adds it as a first-class requirement |
| Evaluation | Amazon Bedrock Evaluations (managed) + RAGAS (open-source, for fast CI) | Native evals are the compliance-facing artifact; RAGAS gives cheap/fast feedback in CI before an evaluation job runs |
| UI | Streamlit, dual-mode (local Strands / deployed AgentCore) | Matches reference repo, fastest path to a working demo |
| Language | Python 3.11+ | Matches Strands, Comprehend Medical boto3 SDK, reference repo |

## 2. Goals and non-goals

**Goals for this repository:**
- A runnable, end-to-end demo: ingest synthetic clinical notes → agentic hybrid retrieval (dense + sparse ontology) → rerank → guardrailed, cited generation → evaluated.
- Terraform that stands up every AWS resource needed, in a `dev` environment, from a clean account.
- Enough test coverage and CI to prove the pipeline works without needing a human to click through the console.

**Explicit non-goals for v1 — do not build these, stub or document them as follow-up work instead:**
- A real Epic/HealthLake connection. Use a mocked FHIR endpoint (a small FastAPI or static-JSON responder) that returns the same shape of data HealthLake would.
- Multi-cloud (Azure) — out of scope entirely for this repo.
- HITRUST certification evidence collection or a policy-as-code gate — document where it *would* plug in, don't build it.
- Real clinician SSO / SMART-on-FHIR launch — use a mocked JWT with configurable `patient_scope` claims for local dev; leave a clearly marked extension point for real Cognito/Entra federation via AgentCore Identity.
- Multi-region DR.

---

## 3. Repository structure

```
clinical-agentic-rag/
├── README.md
├── SPEC.md                        # this file
├── docs/                          # architecture doc + glossary go here if supplied
├── .env.example
├── pyproject.toml
├── infra/
│   ├── envs/dev/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfvars.example
│   └── modules/
│       ├── network/                # minimal VPC/subnets for Aurora
│       ├── data_aurora/             # Aurora Serverless v2 cluster + pgvector bootstrap
│       ├── knowledge_base/          # Bedrock KB resource, pointed at Aurora
│       ├── ingestion/               # S3 buckets + IAM for Comprehend Medical
│       ├── agentcore/               # agent_runtime, gateway, memory, identity
│       ├── guardrails/              # bedrock guardrail resource + policy
│       └── observability/           # log groups, CloudWatch Transaction Search setup
├── ingestion/
│   ├── seed_data/
│   │   ├── fhir/                    # synthetic FHIR R4 patient JSON (model after the reference repo's samples)
│   │   └── notes/                   # synthetic free-text clinical notes
│   ├── deidentify.py                # Comprehend Medical DetectPHI wrapper
│   ├── ontology_link.py             # InferICD10CM / InferSNOMEDCT / InferRxNorm wrapper
│   ├── chunk.py
│   ├── embed_and_load.py            # Titan v2 embeddings -> Aurora bedrock_kb table
│   └── ontology_index_load.py       # writes ontology_index table
├── agent/
│   ├── harness_config.yaml          # AgentCore Harness: model, system prompt ref, memory, gateway refs
│   ├── system_prompt.md
│   ├── supervisor.py                # Strands "Agent-as-Tools" orchestrator
│   ├── tools/
│   │   ├── kb_hybrid_retrieve.py
│   │   ├── ontology_lookup.py
│   │   ├── fhir_query.py
│   │   └── rerank.py
│   ├── identity.py                  # mocked JWT / scope-check middleware, extension point noted
│   └── runtime_entrypoint.py        # AgentCore Runtime entrypoint
├── evals/
│   ├── golden_questions.jsonl
│   ├── run_bedrock_evaluations.py
│   └── run_ragas_ci.py
├── ui/
│   └── streamlit_app.py
├── tests/
│   ├── unit/                        # no AWS calls, mocked via moto/fixtures
│   └── integration/                 # marked @pytest.mark.aws, real creds, run manually
└── scripts/
    ├── prereq.sh
    ├── deploy.sh
    └── seed_demo_data.sh
```

---

## 4. Data model (Aurora PostgreSQL)

Two tables, matching the two retrieval tools:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Managed by Bedrock Knowledge Base (dense + sparse hybrid search)
CREATE SCHEMA IF NOT EXISTS bedrock_integration;
CREATE TABLE bedrock_integration.bedrock_kb (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding vector(1024),                 -- Titan Text Embeddings V2 dimension
  chunks text,
  metadata jsonb,
  custom_metadata jsonb                   -- patient_scope, source_note_id, note_type, encounter_date
);
CREATE INDEX ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (to_tsvector('english', chunks));
CREATE INDEX ON bedrock_integration.bedrock_kb USING gin (custom_metadata);

-- Sparse ontology index — separate from the KB table; see architecture doc §"Where your ask needs a design decision"
CREATE TABLE ontology_index (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid REFERENCES bedrock_integration.bedrock_kb(id),
  entity_text text NOT NULL,
  code_system text NOT NULL CHECK (code_system IN ('ICD10CM','SNOMEDCT','RXNORM')),
  code text NOT NULL,
  description text,
  confidence numeric,
  patient_scope text,                     -- mirrors the KB row's scope for consistent access filtering
  created_at timestamptz DEFAULT now()
);
CREATE INDEX ON ontology_index USING gin (entity_text gin_trgm_ops);
CREATE INDEX ON ontology_index (code_system, code);
CREATE INDEX ON ontology_index (patient_scope);
```

Exact column/index syntax for the `bedrock_kb` table must match whatever Bedrock's current Aurora KB prerequisites document specifies at build time — verify against `docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html` before finalizing the migration, since Bedrock enforces specific column names for its managed table.

---

## 5. Infrastructure (Terraform)

Build one `dev` environment under `infra/envs/dev/`, composed from the modules below. **Before hand-writing the `agentcore` module, run `agentcore create --template production --iac terraform`** (AWS's official starter toolkit) in a scratch directory and use its generated Terraform as a reference/starting point for the `agent_runtime`, `gateway`, and `memory` resources — don't reinvent resource configuration the toolkit already gets right.

| Module | Provisions | Notes |
|---|---|---|
| `network` | Minimal VPC, 2 private subnets, security group for Aurora | Keep small — this isn't a multi-AZ production network design for v1 |
| `data_aurora` | Aurora Serverless v2 PostgreSQL cluster, `pgvector`/`pg_trgm` extensions bootstrapped via a `null_resource`/Lambda-backed custom resource, Secrets Manager credential | Confirm current Bedrock-supported pgvector version before pinning the engine version |
| `knowledge_base` | Bedrock Knowledge Base resource pointed at the Aurora cluster, hybrid search enabled, S3 data source for raw notes | Verify the exact Terraform resource name in the AWS provider docs at build time (Knowledge Bases live under the `bedrockagent` service namespace, not `bedrockagentcore`) |
| `ingestion` | S3 buckets (raw notes, seed FHIR), IAM role/policy for Comprehend Medical (`comprehendmedical:DetectPHI`, `InferICD10CM`, `InferSNOMEDCT`, `InferRxNorm`) | Least-privilege — scope to the specific bucket ARNs |
| `agentcore` | `aws_bedrockagentcore_agent_runtime`, `aws_bedrockagentcore_gateway`, `aws_bedrockagentcore_memory`, associated IAM execution role | Agent Runtime requires ARM64-compatible packaging — confirm build target |
| `guardrails` | Bedrock Guardrail resource (verify current resource name — likely under the `bedrock` service namespace) with sensitive-info filters, denied topics, prompt-attack protection | See §7 for the policy content |
| `observability` | CloudWatch log groups, CloudWatch Transaction Search enablement for AgentCore Observability | One-time account-level setup step may be required outside Terraform — document it in the module's README if so |

**Definition of Done for Phase 1:** `terraform plan` is clean with no errors in `dev`; after `terraform apply`, the Aurora cluster is reachable and the schema migration from §4 runs successfully via the RDS Data API.

---

## 6. Ingestion pipeline

Mirrors the architecture document's Phase 1, built against **synthetic data only**:

1. **Seed data** (`ingestion/seed_data/`) — model the FHIR samples after the reference repo's format (`Patient`, `Condition`, `Observation`, `MedicationRequest` resources with realistic-but-fictional values); write 8–12 synthetic free-text notes with intentionally clinically-interesting content (e.g., one note mentioning an adverse reaction to contrast dye under an unusual phrasing, to make the multi-step retrieval demo meaningful).
2. **`deidentify.py`** — wraps `comprehendmedical:DetectPHI`. Even though seed data has no real PHI, run it for real so the code path is exercised and demonstrably correct.
3. **`ontology_link.py`** — wraps `InferICD10CM`, `InferSNOMEDCT`, `InferRxNorm`; writes results to `ontology_index`.
4. **`chunk.py`** — section-aware chunking (split on common clinical note headers: HPI, Assessment, Plan, Medications; fall back to fixed-size with overlap if headers aren't found).
5. **`embed_and_load.py`** — Titan V2 embeddings, writes to `bedrock_integration.bedrock_kb`, sets `custom_metadata.patient_scope` for later access filtering.
6. **`scripts/seed_demo_data.sh`** — runs the whole pipeline end-to-end against the seed data in one command.

**Definition of Done for Phase 3:** running `seed_demo_data.sh` against a fresh dev environment populates both tables; a smoke-test query against the KB's `Retrieve` API returns non-empty, correctly-scoped results.

---

## 7. Agent, tools, and guardrails

### Supervisor pattern
`agent/supervisor.py` implements the same **"Agent-as-Tools"** pattern as the reference repo: one supervisor agent routes to specialized capability, but here the specialization is by *retrieval strategy* rather than by clinical domain — the supervisor decides whether a question needs ontology resolution, semantic search, structured FHIR lookup, or some sequence of the three (see the architecture document's Step 10 walkthrough for the exact multi-step example to replicate in a test).

### Tool contracts

```python
def kb_hybrid_retrieve(query: str, patient_scope: str, top_k: int = 10) -> list[RetrievedChunk]:
    """Dense+sparse hybrid search over bedrock_kb, scoped by patient_scope."""

def ontology_lookup(term: str, code_systems: list[str] = ["ICD10CM", "SNOMEDCT", "RXNORM"], top_k: int = 5) -> list[OntologyMatch]:
    """Fuzzy/exact search over ontology_index using pg_trgm similarity."""

def fhir_query(patient_id: str, resource_type: str, params: dict) -> FHIRBundle:
    """Structured lookup against the mocked FHIR endpoint (Phase 0 non-goal note: swap for real HealthLake later)."""

def rerank(query: str, candidates: list[str], top_k: int) -> list[RerankedResult]:
    """Bedrock Rerank API call using Cohere Rerank 3.5."""
```

### System prompt (`agent/system_prompt.md`)
Port the five rules from the architecture document's Step 8 verbatim: answer only from retrieved/cited context; every clinical claim cites a source note ID; say so if retrieval returns nothing relevant; frame answers as decision support, never a directive; refuse anything outside the session's authorized patient scope.

### Guardrails policy (`infra/modules/guardrails`)
- **Sensitive information filters:** built-in PII entity types (names, SSNs, addresses, phone numbers) plus a custom regex for the seed data's MRN format.
- **Denied topics:** definitive diagnosis statements, treatment directives phrased as instructions rather than decision support.
- **Prompt-attack protection:** enabled.
- Applied on **both** input and output of every generation call — wire this at the point in `supervisor.py` where the final Bedrock model invocation happens, not just at the API boundary.

**Definition of Done for Phase 4/5:** a local run (`AGENT_MODE=local`) correctly answers the seed data's "adverse reaction to contrast dye"-style question via the multi-step path (resolve term → broaden search → notice gap → retrieve again → rerank → cite); a guardrail test proves a cross-patient-scope prompt injection is blocked before reaching the model.

---

## 8. Evaluation

- **`evals/golden_questions.jsonl`** — one line per test case: `{"question": ..., "patient_scope": ..., "expected_citations": [...], "expected_answer_contains": [...]}`. Write at least 10, covering: a pure-dense case, a pure-sparse/ontology case, a case that requires the multi-step follow-up retrieval, and at least one case that should trigger a guardrail refusal.
- **`evals/run_ragas_ci.py`** — runs RAGAS's `faithfulness`, `context_precision`, `context_recall` against the golden set on every PR, using a small fixed subset for speed; wire into GitHub Actions as a required check.
- **`evals/run_bedrock_evaluations.py`** — launches a real Bedrock Evaluations job (retrieve-only: context relevance/coverage; retrieve-and-generate: correctness, completeness, faithfulness, citation precision/coverage) against the KB — this is a manually-triggered script, not a CI gate, since it costs money and takes longer.

**Definition of Done for Phase 7:** CI fails a PR if RAGAS faithfulness drops below a defined threshold on the golden set; `run_bedrock_evaluations.py` successfully launches and reports a job ID.

---

## 9. UI

`ui/streamlit_app.py`, two modes exactly like the reference repo:
- `AGENT_MODE=local` — runs the Strands supervisor directly in-process.
- `AGENT_MODE=agentcore` — calls the deployed AgentCore Runtime via `bedrock-agent-runtime` `InvokeAgentRuntime`.

**Definition of Done for Phase 8:** `streamlit run ui/streamlit_app.py` in either mode answers a question end-to-end with visible citations.

---

## 10. Testing & CI

- **Unit tests** (`tests/unit/`): no real AWS calls — mock boto3 clients (`moto` where it covers the service, hand-written fixtures where it doesn't, e.g. Comprehend Medical and Bedrock Rerank aren't in moto's coverage as of this writing — verify and stub accordingly).
- **Integration tests** (`tests/integration/`): marked `@pytest.mark.aws`, require real credentials and a deployed `dev` environment, run manually or on a nightly schedule — never on every PR.
- **CI pipeline**: `terraform validate` + `tflint` on the `infra/` changes; `pytest tests/unit`; `evals/run_ragas_ci.py` as described above.

---

## 11. Environment configuration (`.env.example`)

```
AWS_REGION=us-east-1
AWS_PROFILE=
AURORA_CLUSTER_ARN=
AURORA_SECRET_ARN=
KNOWLEDGE_BASE_ID=
BEDROCK_GUARDRAIL_ID=
BEDROCK_GUARDRAIL_VERSION=
AGENTCORE_RUNTIME_ARN=
AGENT_MODE=local            # local | agentcore
TITAN_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
RERANK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0
MOCK_FHIR_ENDPOINT_URL=http://localhost:8000
```

---

## 12. Build order (execute in this sequence)

1. **Phase 0 — Scaffold.** Repo structure, `pyproject.toml`, `.env.example`, empty test suite green. *Ask nothing, just build.*
2. **Phase 1 — Terraform foundation.** Network + Aurora + S3 + IAM. **Ask before `terraform apply`** — this is the first step that costs money.
3. **Phase 2 — Knowledge Base.** Bedrock KB wired to Aurora, hybrid search on, smoke-tested.
4. **Phase 3 — Ingestion.** Seed data + full pipeline, both tables populated.
5. **Phase 4 — Agent & tools.** Supervisor + 4 tools, local mode working against seed data.
6. **Phase 5 — Guardrails & Identity.** Policy wired in, mocked scope enforcement tested.
7. **Phase 6 — AgentCore deployment.** Terraform `agentcore` module, `deploy.sh`, `agentcore invoke` working against the deployed runtime.
8. **Phase 7 — Evaluation.** Golden set, RAGAS in CI, Bedrock Evaluations script.
9. **Phase 8 — UI.** Streamlit, both modes.

At the end of each phase, run its Definition of Done before starting the next. If a DoD fails, fix it — don't proceed with a known-broken foundation.

---

## 13. References

- Architecture document and concept glossary this spec was derived from (place in `docs/` if available)
- Reference implementation: [aws-samples/sample-bedrock-agentcore-healthcare-s3vectors](https://github.com/aws-samples/sample-bedrock-agentcore-healthcare-s3vectors)
- [AgentCore starter toolkit — `agentcore create`](https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/create/quickstart.html)
- [Terraform AWS provider — `aws_bedrockagentcore_agent_runtime`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime)
- [Bedrock Knowledge Bases — Aurora PostgreSQL setup](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
- [Bedrock Rerank API](https://docs.aws.amazon.com/bedrock/latest/userguide/rerank.html)
- [Bedrock Guardrails — sensitive information filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)
- [Bedrock RAG evaluation metrics](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-eval-retrieve-generate.html)
- [Amazon Comprehend Medical API reference](https://docs.aws.amazon.com/comprehend-medical/latest/dev/comprehendmedical-howitworks.html)

---

## Kickoff prompt (copy-paste this to Claude Code alongside this file)

> Read SPEC.md in full. Execute Phase 0 now. Stop and summarize what you built before starting Phase 1 — Phase 1 onward touches real AWS resources and costs money, so confirm with me before running `terraform apply` or any other billable command. Work through the phases in order, running each Definition of Done before moving to the next, and tell me explicitly if any AWS API/Terraform resource referenced in this spec doesn't match what you find in current documentation — verify rather than assume for anything marked "verify at build time."
