"""Strands 'Agent-as-Tools' supervisor (SPEC.md §7).

One supervisor agent routes to specialized capability by *retrieval strategy*:
ontology resolution, semantic (hybrid) search, structured FHIR lookup, reranking,
or the composed multi-step strategy in ``agent.retrieval_strategy``.

The real run (Bedrock model + live tools) is exercised in DEPLOY.md §4. Locally,
``build_tools`` / ``build_supervisor`` assemble without credentials, and the
routing logic is unit-tested through ``agent.retrieval_strategy`` with fakes.

GUARDRAIL WIRE POINT (Phase 5): the final model invocation inside ``answer`` must
be wrapped with Bedrock Guardrails on both input and output — see
``_guarded_prompt`` / ``_guard_output`` placeholders below.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent import retrieval_strategy
from agent.tools.fhir_query import fhir_query as _fhir_query
from agent.tools.kb_hybrid_retrieve import kb_hybrid_retrieve as _kb_hybrid_retrieve
from agent.tools.ontology_lookup import ontology_lookup as _ontology_lookup
from agent.tools.rerank import rerank as _rerank

SYSTEM_PROMPT_PATH = Path(__file__).with_name("system_prompt.md")
TOOL_NAMES = (
    "ontology_lookup",
    "kb_hybrid_retrieve",
    "fhir_query",
    "rerank",
    "multi_step_retrieve",
)


@dataclass
class SupervisorConfig:
    knowledge_base_id: str | None = None
    aurora_cluster_arn: str | None = None
    aurora_secret_arn: str | None = None
    aurora_database: str = "clinical_rag"
    fhir_base_url: str | None = None
    rerank_model_arn: str | None = None
    region: str | None = None

    @classmethod
    def from_env(cls) -> SupervisorConfig:
        return cls(
            knowledge_base_id=os.environ.get("KNOWLEDGE_BASE_ID"),
            aurora_cluster_arn=os.environ.get("AURORA_CLUSTER_ARN"),
            aurora_secret_arn=os.environ.get("AURORA_SECRET_ARN"),
            aurora_database=os.environ.get("AURORA_DATABASE_NAME", "clinical_rag"),
            fhir_base_url=os.environ.get("MOCK_FHIR_ENDPOINT_URL"),
            rerank_model_arn=os.environ.get("RERANK_MODEL_ARN"),
            region=os.environ.get("AWS_REGION"),
        )


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text()


# --------------------------------------------------------------------------- #
# Plain callables bound to config — used by the strategy and wrapped as tools  #
# --------------------------------------------------------------------------- #
def bound_callables(config: SupervisorConfig) -> dict[str, Callable[..., Any]]:
    def ontology_lookup(
        term: str, code_systems: list[str] | None = None, top_k: int = 5, **kw: Any
    ):
        return _ontology_lookup(
            term,
            code_systems,
            top_k,
            patient_scope=kw.get("patient_scope"),
            resource_arn=config.aurora_cluster_arn,
            secret_arn=config.aurora_secret_arn,
            database=config.aurora_database,
            region=config.region,
        )

    def kb_hybrid_retrieve(query: str, patient_scope: str, top_k: int = 10, **kw: Any):
        return _kb_hybrid_retrieve(
            query,
            patient_scope,
            top_k,
            knowledge_base_id=config.knowledge_base_id,
            region=config.region,
        )

    def rerank(query: str, candidates: list[str], top_k: int, **kw: Any):
        return _rerank(
            query, candidates, top_k, model_arn=config.rerank_model_arn, region=config.region
        )

    def fhir_query(patient_id: str, resource_type: str, params: dict, **kw: Any):
        return _fhir_query(patient_id, resource_type, params, base_url=config.fhir_base_url)

    return {
        "ontology_lookup": ontology_lookup,
        "kb_hybrid_retrieve": kb_hybrid_retrieve,
        "rerank": rerank,
        "fhir_query": fhir_query,
    }


class _ToolBundle:
    """Adapter so bound callables satisfy retrieval_strategy.Tools."""

    def __init__(self, calls: dict[str, Callable[..., Any]]) -> None:
        self.ontology_lookup = calls["ontology_lookup"]
        self.kb_hybrid_retrieve = calls["kb_hybrid_retrieve"]
        self.rerank = calls["rerank"]


def build_tools(config: SupervisorConfig | None = None) -> list[Any]:
    """Return the Strands ``@tool`` objects the supervisor exposes."""
    from strands import tool

    config = config or SupervisorConfig.from_env()
    calls = bound_callables(config)

    @tool
    def ontology_lookup(
        term: str, patient_scope: str, code_systems: list[str] | None = None
    ) -> list[dict]:
        """Resolve a clinical term to ICD-10-CM / SNOMED CT / RxNorm codes via fuzzy match."""
        return [
            m.model_dump()
            for m in calls["ontology_lookup"](term, code_systems, patient_scope=patient_scope)
        ]

    @tool
    def kb_hybrid_retrieve(query: str, patient_scope: str, top_k: int = 10) -> list[dict]:
        """Dense+sparse hybrid search over the clinical notes, scoped to one patient."""
        return [c.model_dump() for c in calls["kb_hybrid_retrieve"](query, patient_scope, top_k)]

    @tool
    def fhir_query(patient_id: str, resource_type: str, params: dict | None = None) -> dict:
        """Structured FHIR lookup (Condition/Observation/MedicationRequest) for one patient."""
        return calls["fhir_query"](patient_id, resource_type, params or {}).model_dump()

    @tool
    def rerank(query: str, candidates: list[str], top_k: int = 5) -> list[dict]:
        """Re-order candidate passages by relevance to the query (Cohere Rerank 3.5)."""
        return [r.model_dump() for r in calls["rerank"](query, candidates, top_k)]

    @tool
    def multi_step_retrieve(query: str, patient_scope: str, top_k: int = 10) -> dict:
        """Resolve terms, search, notice gaps, broaden, retrieve again, then rerank. Use for
        questions that mix a named condition/drug with a descriptive clinical detail."""
        result = retrieval_strategy.hybrid_multistep(
            query, patient_scope, tools=_ToolBundle(calls), top_k=top_k
        )
        return {
            "chunks": [c.model_dump() for c in result.chunks],
            "tool_sequence": result.tool_sequence,
            "broadened": result.broadened,
        }

    return [ontology_lookup, kb_hybrid_retrieve, fhir_query, rerank, multi_step_retrieve]


def _build_model(config: SupervisorConfig) -> Any:
    from strands.models import BedrockModel

    # GUARDRAIL WIRE POINT (Phase 5): pass guardrail id/version into the model
    # config (or wrap invocations) so both input and output are filtered.
    return BedrockModel(region_name=config.region)


def build_supervisor(
    *,
    mode: str = "local",
    config: SupervisorConfig | None = None,
    model: Any = None,
) -> Any:
    """Assemble the Strands supervisor Agent. ``model`` may be injected for tests."""
    from strands import Agent

    config = config or SupervisorConfig.from_env()
    if model is None:
        model = _build_model(config)
    return Agent(
        model=model,
        tools=build_tools(config),
        system_prompt=load_system_prompt(),
    )


def _guarded_prompt(text: str) -> str:
    # Phase 5: run Bedrock Guardrails on the input side here.
    return text


def _guard_output(text: str) -> str:
    # Phase 5: run Bedrock Guardrails on the output side here.
    return text


def answer(query: str, patient_scope: str, *, mode: str = "local", **kw: Any) -> dict:
    """Run the supervisor for one question. Real Bedrock call — see DEPLOY.md §4."""
    supervisor = build_supervisor(mode=mode, **kw)
    result = supervisor(_guarded_prompt(f"[patient_scope={patient_scope}] {query}"))
    text = _guard_output(str(result))
    return {"answer": text, "patient_scope": patient_scope}
