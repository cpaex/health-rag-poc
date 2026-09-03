"""Phase 0 scaffold sanity checks. Superseded by real unit tests in later phases."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PATHS = [
    "pyproject.toml",
    ".env.example",
    "README.md",
    "SPEC.md",
    "DEPLOY.md",
    "infra/envs/dev",
    "infra/modules/network",
    "infra/modules/data_aurora",
    "infra/modules/knowledge_base",
    "infra/modules/ingestion",
    "infra/modules/agentcore",
    "infra/modules/guardrails",
    "infra/modules/observability",
    "ingestion/deidentify.py",
    "ingestion/ontology_link.py",
    "ingestion/chunk.py",
    "ingestion/embed_and_load.py",
    "ingestion/ontology_index_load.py",
    "ingestion/seed_data/fhir",
    "ingestion/seed_data/notes",
    "agent/supervisor.py",
    "agent/retrieval_strategy.py",
    "agent/guardrails.py",
    "agent/models.py",
    "agent/identity.py",
    "agent/runtime_entrypoint.py",
    "mocks/fhir_server.py",
    "Dockerfile",
    "infra/modules/agentcore/main.tf",
    "infra/modules/observability/main.tf",
    "agent/system_prompt.md",
    "agent/harness_config.yaml",
    "agent/tools/kb_hybrid_retrieve.py",
    "agent/tools/ontology_lookup.py",
    "agent/tools/fhir_query.py",
    "agent/tools/rerank.py",
    "evals/golden_questions.jsonl",
    "evals/run_ragas_ci.py",
    "evals/run_bedrock_evaluations.py",
    "ui/streamlit_app.py",
    "scripts/prereq.sh",
    "scripts/deploy.sh",
    "scripts/seed_demo_data.sh",
    "scripts/apply_sql.py",
    "scripts/kb_smoke_test.py",
    "scripts/run_mock_fhir.sh",
]


@pytest.mark.parametrize("rel", EXPECTED_PATHS)
def test_scaffold_path_exists(rel: str) -> None:
    assert (ROOT / rel).exists(), f"missing scaffold path: {rel}"


def test_env_example_has_required_keys() -> None:
    text = (ROOT / ".env.example").read_text()
    for key in ("AWS_REGION", "AGENT_MODE", "TITAN_EMBEDDING_MODEL_ID", "RERANK_MODEL_ARN"):
        assert key in text
