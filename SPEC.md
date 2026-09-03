# SPEC.md — Clinical Agentic RAG Starter Repository

This is a build specification for **Claude Code**. It describes a repository to scaffold from scratch: an agentic, hybrid-retrieval RAG platform over clinical notes, built on Amazon Bedrock AgentCore. Follow the phases in order; treat each phase's "Definition of Done" as a gate before moving to the next.

**This build produces local files only.** No phase runs `terraform apply`, `terraform plan`, `agentcore deploy`, a real Bedrock/Comprehend Medical/model API call, or any other command that creates AWS resources or incurs billing. Every phase's Definition of Done is verifiable locally: `terraform fmt` / `terraform validate` / `tflint`, `ruff`, `pytest tests/unit` (AWS mocked), file-structure checks, and shell lint. Anything that needs live AWS — provisioning, schema migration against a real cluster, KB ingestion, seed-data runs, agent runs against Bedrock, managed evaluations, end-to-end UI checks — is **not executed during the build**. Instead it is documented, as an ordered, copy-pasteable runbook, in **`DEPLOY.md`**, which is authored incrementally as the phases progress and finalized in **Phase 9**.

> Companion reading (not required to build, but explains the *why* behind these choices): the architecture document and concept glossary this spec was derived from. If they're present in `docs/`, read them before Phase 1.

> **`DEPLOY.md` contract.** Each phase that defines AWS resources or live steps appends a correspondingly-numbered section to `DEPLOY.md` covering: exact prerequisites (credentials, region, Bedrock model access to enable, account-level toggles), the ordered `terraform apply` invocation for that phase's modules (including any `-target` sequencing and `terraform output` values to capture), post-apply manual steps with the command for each, a verification command with expected output, and a teardown note. Phase 9 assembles these into one front-to-back runbook plus a consolidated teardown (`terraform destroy` order + cost notes). `DEPLOY.md` is the *only* place `terraform apply` and billable commands appear.

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
├── DEPLOY.md                      # ordered runbook: terraform apply + post-apply steps for every resource (see Phase 9)
├── Dockerfile                     # ARM64 AgentCore Runtime image (Phase 6)
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
│   ├── supervisor.py                # Strands "Agent-as-Tools" orchestrator; identity + guardrails wired in answer()
│   ├── retrieval_strategy.py        # deterministic multi-step retrieve (arch doc Step 10), unit-tested
│   ├── guardrails.py                # bedrock-runtime:ApplyGuardrail wrapper (input + output)
│   ├── models.py                    # pydantic tool-contract types
│   ├── tools/
│   │   ├── kb_hybrid_retrieve.py
│   │   ├── ontology_lookup.py
│   │   ├── fhir_query.py
│   │   └── rerank.py
│   ├── identity.py                  # mocked JWT / scope-check middleware, extension point noted
│   └── runtime_entrypoint.py        # AgentCore Runtime entrypoint
├── mocks/
│   └── fhir_server.py               # FastAPI mocked FHIR R4 endpoint over the seed Bundles (§2 non-goal)
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
    ├── apply_sql.py                 # RDS Data API SQL runner (schema bootstrap + verify)
    ├── kb_smoke_test.py             # KB Retrieve HYBRID smoke test
    ├── run_mock_fhir.sh
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

Build one `dev` environment under `infra/envs/dev/`, composed from the modules below. All modules are **written and validated locally only** — every `terraform apply` is deferred to `DEPLOY.md` (see Phase 9). **Before hand-writing the `agentcore` module, run `agentcore create --template production --iac terraform`** (AWS's official starter toolkit) in a scratch directory and use its generated Terraform as a reference/starting point for the `agent_runtime`, `gateway`, and `memory` resources — don't reinvent resource configuration the toolkit already gets right. (`agentcore create` only scaffolds local files; any `agentcore deploy`/`launch`/`invoke` belongs in `DEPLOY.md`.)

| Module | Provisions | Notes |
|---|---|---|
| `network` | Minimal VPC, 2 private subnets, security group for Aurora | Keep small — this isn't a multi-AZ production network design for v1 |
| `data_aurora` | Aurora Serverless v2 PostgreSQL cluster, `pgvector`/`pg_trgm` extensions bootstrapped via a `null_resource`/Lambda-backed custom resource, Secrets Manager credential | Confirm current Bedrock-supported pgvector version before pinning the engine version |
| `knowledge_base` | Bedrock Knowledge Base resource pointed at the Aurora cluster, hybrid search enabled, S3 data source for raw notes | Verify the exact Terraform resource name in the AWS provider docs at build time (Knowledge Bases live under the `bedrockagent` service namespace, not `bedrockagentcore`) |
| `ingestion` | S3 buckets (raw notes, seed FHIR), IAM role/policy for Comprehend Medical (`comprehendmedical:DetectPHI`, `InferICD10CM`, `InferSNOMEDCT`, `InferRxNorm`) | Least-privilege — scope to the specific bucket ARNs |
| `agentcore` | `aws_bedrockagentcore_agent_runtime`, `aws_bedrockagentcore_gateway`, `aws_bedrockagentcore_memory`, associated IAM execution role | Agent Runtime requires ARM64-compatible packaging — confirm build target |
| `guardrails` | Bedrock Guardrail resource (verify current resource name — likely under the `bedrock` service namespace) with sensitive-info filters, denied topics, prompt-attack protection | See §7 for the policy content |
| `observability` | CloudWatch log groups, CloudWatch Transaction Search enablement for AgentCore Observability | One-time account-level setup step may be required outside Terraform — document it in the module's README **and in `DEPLOY.md` §6** if so |

**Definition of Done for Phase 1 (local only):** `terraform fmt -check`, `terraform validate`, and `tflint` all pass clean for the `network`, `data_aurora`, and `ingestion` modules and the `dev` env. The `null_resource` and any helper script (e.g. `scripts/apply_sql.py`) that will run the §4 migration exist and are lint-clean. No `terraform plan`/`apply` is run here (both need credentials).

**Deferred to `DEPLOY.md` §1:** `aws sso login` / credential + region setup; `terraform -chdir=infra/envs/dev init`; `terraform plan` review; `terraform apply` for `network` + `data_aurora` + `ingestion`; confirm the Aurora cluster is reachable and the §4 schema migration ran via the RDS Data API; capture `terraform output` into `.env`.

---

## 6. Ingestion pipeline

Mirrors the architecture document's Phase 1, built against **synthetic data only**:

1. **Seed data** (`ingestion/seed_data/`) — model the FHIR samples after the reference repo's format (`Patient`, `Condition`, `Observation`, `MedicationRequest` resources with realistic-but-fictional values); write 8–12 synthetic free-text notes with intentionally clinically-interesting content (e.g., one note mentioning an adverse reaction to contrast dye under an unusual phrasing, to make the multi-step retrieval demo meaningful).
2. **`deidentify.py`** — wraps `comprehendmedical:DetectPHI`. Even though seed data has no real PHI, run it for real so the code path is exercised and demonstrably correct.
3. **`ontology_link.py`** — wraps `InferICD10CM`, `InferSNOMEDCT`, `InferRxNorm`; writes results to `ontology_index`.
4. **`chunk.py`** — section-aware chunking (split on common clinical note headers: HPI, Assessment, Plan, Medications; fall back to fixed-size with overlap if headers aren't found).
5. **`embed_and_load.py`** — Titan V2 embeddings, writes to `bedrock_integration.bedrock_kb`, sets `custom_metadata.patient_scope` for later access filtering.
6. **`scripts/seed_demo_data.sh`** — runs the whole pipeline end-to-end against the seed data in one command.

> Phase 2 (Knowledge Base module) has no separate section here; its `knowledge_base` Terraform module is listed in §5. **Definition of Done for Phase 2 (local only):** `terraform validate` + `tflint` pass for the `knowledge_base` module and `dev` env; the `Retrieve`-API smoke-test script (`scripts/kb_smoke_test.py`) exists, requests `overrideSearchType=HYBRID`, applies the `patient_scope` filter, and is unit-tested with a mocked client. **Deferred to `DEPLOY.md` §2:** `terraform apply` for `knowledge_base`; run `kb_smoke_test.py` (expect zero results pre-ingestion, non-empty after Phase 3's data load).

**Definition of Done for Phase 3 (local only):** each pipeline module (`deidentify.py`, `ontology_link.py`, `chunk.py`, `embed_and_load.py`, `ontology_index_load.py`) imports cleanly and is unit-tested with mocked boto3 / hand-written fixtures (Comprehend Medical + Titan + RDS Data API all mocked — no real calls); `chunk.py`'s section-aware splitting is tested on the seed notes directly; the 8–12 synthetic FHIR resources and free-text notes exist under `ingestion/seed_data/`; `scripts/seed_demo_data.sh` is written and shell-lint-clean.

**Deferred to `DEPLOY.md` §3:** run `seed_demo_data.sh` against the deployed dev environment; confirm both `bedrock_integration.bedrock_kb` and `ontology_index` are populated; run `kb_smoke_test.py` and confirm non-empty, correctly patient-scoped `Retrieve` results.

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

**Definition of Done for Phase 4/5 (local only):**
- `supervisor.py` and all four tools import cleanly; the supervisor's routing/multi-step-planning logic is unit-tested with **mocked tools** (no Bedrock calls) — including a test that replays the "adverse reaction to contrast dye" scenario (resolve term → broaden search → notice gap → retrieve again → rerank → cite) and asserts the tool-call sequence.
- `identity.py` scope enforcement is unit-tested: a cross-patient-scope request (and a prompt-injection string that tries to widen scope) is rejected **before** any tool/model call.
- The guardrail wiring point in `supervisor.py` (input + output of the final model invocation) is present and unit-tested with a stubbed guardrail client asserting both directions are checked.
- `terraform validate` + `tflint` pass for the `guardrails` module and `dev` env.

**Deferred to `DEPLOY.md` §4–5:** `terraform apply` for `guardrails`; a real `AGENT_MODE=local` run against the deployed KB + Bedrock model answering the contrast-dye question via the multi-step path with visible citations; a live guardrail test showing a cross-scope prompt injection blocked before the model.

---

## 8. Evaluation

- **`evals/golden_questions.jsonl`** — one line per test case: `{"question": ..., "patient_scope": ..., "expected_citations": [...], "expected_answer_contains": [...]}`. Write at least 10, covering: a pure-dense case, a pure-sparse/ontology case, a case that requires the multi-step follow-up retrieval, and at least one case that should trigger a guardrail refusal.
- **`evals/run_ragas_ci.py`** — runs RAGAS's `faithfulness`, `context_precision`, `context_recall` against the golden set on every PR, using a small fixed subset for speed; wire into GitHub Actions as a required check.
- **`evals/run_bedrock_evaluations.py`** — launches a real Bedrock Evaluations job (retrieve-only: context relevance/coverage; retrieve-and-generate: correctness, completeness, faithfulness, citation precision/coverage) against the KB — this is a manually-triggered script, not a CI gate, since it costs money and takes longer.

**Definition of Done for Phase 7 (local only):** `golden_questions.jsonl` has ≥10 cases covering the four required categories; `run_ragas_ci.py` and `run_bedrock_evaluations.py` import cleanly, parse the golden set, and have their non-AWS logic (subset selection, threshold gate, job-spec assembly) unit-tested with a mocked model/eval client; the GitHub Actions workflow invokes `run_ragas_ci.py` as a required check with a defined faithfulness threshold.

**Deferred to `DEPLOY.md` §7:** a real RAGAS run against the deployed stack to confirm the threshold gate fires; `run_bedrock_evaluations.py` launching an actual Bedrock Evaluations job and reporting a job ID.

---

## 9. UI

`ui/streamlit_app.py`, two modes exactly like the reference repo:
- `AGENT_MODE=local` — runs the Strands supervisor directly in-process.
- `AGENT_MODE=agentcore` — calls the deployed AgentCore Runtime via `bedrock-agent-runtime` `InvokeAgentRuntime`.

**Definition of Done for Phase 8 (local only):** `ui/streamlit_app.py` imports cleanly; the mode-switch logic (`local` vs `agentcore`) and the citation-rendering helper are factored out and unit-tested; `streamlit run ui/streamlit_app.py` starts and renders the input form without error using stubbed/empty backends.

**Deferred to `DEPLOY.md` §8:** running the app in both modes against the deployed stack and answering a question end-to-end with visible citations.

---

## 10. Testing & CI

- **Unit tests** (`tests/unit/`): no real AWS calls — mock boto3 clients (`moto` where it covers the service, hand-written fixtures where it doesn't, e.g. Comprehend Medical and Bedrock Rerank aren't in moto's coverage as of this writing — verify and stub accordingly).
- **Integration tests** (`tests/integration/`): marked `@pytest.mark.aws`, require real credentials and a deployed `dev` environment, run manually or on a nightly schedule — never on every PR.
- **CI pipeline**: `terraform fmt -check` + `terraform validate` + `tflint` on the `infra/` changes; `ruff`; `pytest tests/unit`; `evals/run_ragas_ci.py` as described above. CI never runs `terraform apply` or any billable AWS command — those live only in `DEPLOY.md`.

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

Every phase writes **local files only** and is gated by a local Definition of Done (fmt/validate/tflint, ruff, `pytest tests/unit`, structure/shell lint). No phase runs `terraform apply`, `agentcore deploy/invoke`, or any billable AWS call. Each infra/live phase also **appends its numbered section to `DEPLOY.md`** (the deferred `terraform apply` + post-apply + verification steps).

1. **Phase 0 — Scaffold.** Repo structure, `pyproject.toml`, `.env.example`, `DEPLOY.md` skeleton, empty test suite green.
2. **Phase 1 — Terraform foundation.** `network` + `data_aurora` + `ingestion` modules written & validated. → `DEPLOY.md §1`.
3. **Phase 2 — Knowledge Base.** `knowledge_base` module written & validated; `kb_smoke_test.py` written & unit-tested. → `DEPLOY.md §2`.
4. **Phase 3 — Ingestion.** Seed data + pipeline modules + `seed_demo_data.sh`, all unit-tested with AWS mocked. → `DEPLOY.md §3`.
5. **Phase 4 — Agent & tools.** Supervisor + 4 tools; routing/multi-step logic unit-tested with mocked tools. → `DEPLOY.md §4`.
6. **Phase 5 — Guardrails & Identity.** `guardrails` module + guardrail wiring in `supervisor.py` + `identity.py` scope enforcement, all unit-tested. → `DEPLOY.md §5`.
7. **Phase 6 — AgentCore deployment assets.** `agentcore` + `observability` modules, `deploy.sh`, ARM64 packaging, `runtime_entrypoint.py` — written & validated, not deployed. → `DEPLOY.md §6`.
8. **Phase 7 — Evaluation.** Golden set, `run_ragas_ci.py` (+ GitHub Actions wiring), `run_bedrock_evaluations.py` — non-AWS logic unit-tested. → `DEPLOY.md §7`.
9. **Phase 8 — UI.** Streamlit dual-mode; mode-switch + citation rendering unit-tested; app starts with stub backends. → `DEPLOY.md §8`.
10. **Phase 9 — Deployment guide.** Assemble the per-phase `DEPLOY.md` sections into one ordered front-to-back runbook + consolidated teardown. See §13.

At the end of each phase, run its (local) Definition of Done before starting the next. If a DoD fails, fix it — don't proceed with a known-broken foundation.

---

## 13. Phase 9 — Deployment guide (`DEPLOY.md`)

`DEPLOY.md` is the single runbook that stands the whole system up from a clean AWS account. It is the **only** document containing `terraform apply` and billable commands. Build it incrementally: Phase 0 creates the skeleton; every infra/live phase appends its numbered section; Phase 9 assembles and proof-reads the whole thing.

**Required structure:**

0. **Prerequisites** — AWS account + credentials (`aws sso login` / profile / `AWS_REGION`); Terraform + `tflint` versions; Python env; **Bedrock model access to request in the console** (Titan Text Embeddings V2, Cohere Rerank 3.5, the generation model); any account-level enables (CloudWatch Transaction Search / X-Ray trace ingestion for AgentCore Observability); estimated standing cost of the deployed stack.
1. **§1 Foundation** — `terraform -chdir=infra/envs/dev init`; `plan` review; `apply` (`network`, `data_aurora`, `ingestion`); verify Aurora reachable + §4 migration applied via RDS Data API; `terraform output` → `.env`.
2. **§2 Knowledge Base** — `apply` `knowledge_base`; `python scripts/kb_smoke_test.py --kb-id …` (expect 0 results pre-ingestion).
3. **§3 Ingestion** — upload seed data to S3; `scripts/seed_demo_data.sh`; confirm both tables populated; re-run `kb_smoke_test.py` → non-empty, correctly scoped.
4. **§4 Agent (local mode)** — populate remaining `.env`; run the contrast-dye question via `AGENT_MODE=local`; confirm the multi-step path + citations.
5. **§5 Guardrails & Identity** — `apply` `guardrails`; capture guardrail id/version → `.env`; live cross-scope prompt-injection test shows a block before the model.
6. **§6 AgentCore deploy** — any account-level Observability enable; ARM64 build/package; `apply` `agentcore` + `observability`; `agentcore` (or `bedrock-agent-runtime InvokeAgentRuntime`) invoke against the deployed runtime; `AGENT_MODE=agentcore` smoke.
7. **§7 Evaluation** — live RAGAS run confirming the threshold gate; `python evals/run_bedrock_evaluations.py` → prints a job ID; where to read results.
8. **§8 UI** — `streamlit run ui/streamlit_app.py` in both modes, end-to-end answer with citations.
9. **Teardown** — `terraform destroy` order (reverse of apply; note resources needing manual empt­ying first, e.g. S3 buckets, KB data); what is *not* destroyed (account-level enables, model access, `DEPLOY.md`-created secrets); residual-cost checklist.

Each step: the exact command, the expected output/signal, and a one-line "if this fails" pointer.

---

## 14. References

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

> Read SPEC.md in full. Execute Phase 0 now, then work through the phases in order. This build creates **local files only** — never run `terraform apply`/`plan`, `agentcore deploy`, or any billable AWS command; every deployment step goes into `DEPLOY.md` instead (skeleton in Phase 0, one section appended per infra/live phase, assembled in Phase 9). Run each phase's local Definition of Done before moving on. Tell me explicitly if any AWS API/Terraform resource referenced in this spec doesn't match current documentation — verify rather than assume for anything marked "verify at build time."
