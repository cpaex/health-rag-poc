# Clinical Agentic RAG Starter

An agentic, hybrid-retrieval RAG platform over **synthetic** clinical notes, built on
Amazon Bedrock AgentCore. See [SPEC.md](SPEC.md) for the full build specification,
[DEPLOY.md](DEPLOY.md) for the deploy-it-for-real runbook, and [docs/](docs/) for the
architecture document and glossary (if supplied).

> The repo build creates **local files only** — no `terraform apply`, no billable AWS
> calls. Every deployment step lives in [DEPLOY.md](DEPLOY.md).

> ⚠️ Development uses **synthetic FHIR data only**. No real PHI is processed. The
> de-identification and ontology-linking code paths run against Amazon Comprehend
> Medical for real, so the logic is production-real without touching real data.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold: repo structure, `pyproject.toml`, `.env.example`, `DEPLOY.md` skeleton, green test suite | ✅ done |
| 1 | Terraform foundation: network + Aurora + S3 + IAM | ✅ modules written; `validate`+`tflint` clean; deploy → [DEPLOY.md §1](DEPLOY.md) |
| 2 | Bedrock Knowledge Base wired to Aurora (hybrid search) | ✅ module + `kb_smoke_test.py` written; `validate`+`tflint` clean; deploy → [DEPLOY.md §2](DEPLOY.md) |
| 3 | Ingestion pipeline + seed data | ✅ seed data + pipeline + `seed_demo_data.sh` (`--dry-run` works); unit-tested; deploy → [DEPLOY.md §3](DEPLOY.md) |
| 4 | Supervisor agent + 4 tools (local mode) | ✅ Strands supervisor + 4 tools + multi-step strategy + mock FHIR server; unit-tested (incl. contrast-dye sequence); live run → [DEPLOY.md §4](DEPLOY.md) |
| 5 | Guardrails + mocked identity/scope enforcement | ✅ `aws_bedrock_guardrail` module + `ApplyGuardrail` wrapper (both sides) + `identity.py` scope/escalation guard; unit-tested; deploy → [DEPLOY.md §5](DEPLOY.md) |
| 6 | AgentCore deployment assets | ✅ `agentcore`+`observability` TF modules, ARM64 `Dockerfile`, `runtime_entrypoint.py`, `deploy.sh`; `validate`+`tflint` clean; deploy → [DEPLOY.md §6](DEPLOY.md) |
| 7 | Evaluation: golden set, RAGAS CI, Bedrock Evaluations | ✅ 12-case golden set, `run_ragas_ci.py` (+ `--self-check` in CI), `run_bedrock_evaluations.py`; unit-tested; live run → [DEPLOY.md §7](DEPLOY.md) |
| 8 | Streamlit UI (local + agentcore modes) | ✅ `ui/streamlit_app.py` + `ui/backend.py`; dual-mode dispatch + citations unit-tested; starts headless (HTTP 200); run → [DEPLOY.md §8](DEPLOY.md) |

## Quick start (Phase 0)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest            # empty suite, should pass
```

## Layout

```
infra/       Terraform — one `dev` environment composed from modules/
ingestion/   De-identify → ontology-link → chunk → embed → load pipeline
agent/       Strands "Agent-as-Tools" supervisor + retrieval tools + AgentCore entrypoint
evals/       Golden questions, RAGAS CI check, Bedrock Evaluations launcher
ui/          Streamlit app (dual-mode: local Strands / deployed AgentCore)
tests/       unit/ (mocked, run in CI) and integration/ (@pytest.mark.aws, manual)
scripts/     prereq / deploy / seed helpers
```

## Cost warning

The deployed stack provisions real AWS resources (Aurora Serverless v2, Bedrock KB,
AgentCore runtime, guardrails). **The repo build never runs `terraform apply` or any
billable command** — deployment is a separate, deliberate step you run from
[DEPLOY.md](DEPLOY.md), which includes a standing-cost estimate and a teardown section.
