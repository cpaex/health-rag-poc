# Clinical Agentic RAG Starter

An agentic, hybrid-retrieval RAG platform over **synthetic** clinical notes, built on
Amazon Bedrock AgentCore. See [SPEC.md](SPEC.md) for the full build specification and
[docs/](docs/) for the architecture document and glossary (if supplied).

> ⚠️ Development uses **synthetic FHIR data only**. No real PHI is processed. The
> de-identification and ontology-linking code paths run against Amazon Comprehend
> Medical for real, so the logic is production-real without touching real data.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold: repo structure, `pyproject.toml`, `.env.example`, green empty test suite | ✅ done |
| 1 | Terraform foundation: network + Aurora + S3 + IAM | 🟡 code written; `validate`+`tflint` clean; `plan`/`apply` pending AWS creds |
| 2 | Bedrock Knowledge Base wired to Aurora (hybrid search) | 🟡 module written; `validate`+`tflint` clean; apply + smoke test pending |
| 3 | Ingestion pipeline + seed data | ⬜ |
| 4 | Supervisor agent + 4 tools (local mode) | ⬜ |
| 5 | Guardrails + mocked identity/scope enforcement | ⬜ |
| 6 | AgentCore deployment | ⬜ |
| 7 | Evaluation: golden set, RAGAS CI, Bedrock Evaluations | ⬜ |
| 8 | Streamlit UI (local + agentcore modes) | ⬜ |

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

Phase 1 onward provisions real AWS resources (Aurora Serverless v2, Bedrock KB,
AgentCore runtime, guardrails). Nothing in this repo runs `terraform apply` or any
billable command without explicit confirmation.
