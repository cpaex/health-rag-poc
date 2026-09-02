"""Dense+sparse hybrid search over bedrock_kb, scoped by patient_scope.

Implemented in Phase 4. Backed by the Bedrock Knowledge Base `Retrieve` API with
`overrideSearchType=HYBRID` and a `custom_metadata.patient_scope` filter.
"""

from __future__ import annotations

from agent.models import RetrievedChunk


def kb_hybrid_retrieve(
    query: str, patient_scope: str, top_k: int = 10
) -> list[RetrievedChunk]:
    raise NotImplementedError("Phase 4: wire to Bedrock KB Retrieve API")
