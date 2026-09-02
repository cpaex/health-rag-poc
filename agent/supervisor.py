"""Strands 'Agent-as-Tools' supervisor orchestrator (SPEC.md §7).

One supervisor agent routes to specialized capability by *retrieval strategy*:
ontology resolution, semantic search, structured FHIR lookup, or a sequence of them.
The final Bedrock model invocation must be wrapped with Bedrock Guardrails on BOTH
input and output (SPEC.md §7 'Guardrails policy'). Implemented in Phase 4; guardrails
wired in Phase 5.
"""

from __future__ import annotations


def build_supervisor(*, mode: str = "local"):
    raise NotImplementedError("Phase 4: assemble Strands supervisor + tools")


def run(query: str, patient_scope: str, *, mode: str = "local") -> dict:
    raise NotImplementedError("Phase 4")
