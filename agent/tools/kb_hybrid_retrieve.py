"""Dense+sparse hybrid search over bedrock_kb, scoped by patient_scope (SPEC.md §7).

Backed by the Bedrock Knowledge Base ``Retrieve`` API with
``overrideSearchType = "HYBRID"`` (dense = pgvector HNSW, sparse = the §4 GIN
full-text index) and a ``custom_metadata.patient_scope`` equals filter.

``build_retrieval_config`` is the single source of truth for the hybrid + scope
query shape; ``scripts/kb_smoke_test.py`` imports it too.
"""

from __future__ import annotations

import os
from typing import Any

from agent.models import RetrievedChunk


def build_retrieval_config(top_k: int, patient_scope: str | None) -> dict:
    vsc: dict[str, Any] = {
        "numberOfResults": top_k,
        "overrideSearchType": "HYBRID",
    }
    if patient_scope:
        vsc["filter"] = {"equals": {"key": "patient_scope", "value": patient_scope}}
    return {"vectorSearchConfiguration": vsc}


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("bedrock-agent-runtime", region_name=region)


def _to_chunk(raw: dict, requested_scope: str) -> RetrievedChunk:
    meta = raw.get("metadata", {}) or {}
    # KB flattens custom_metadata keys into `metadata` on Retrieve responses.
    return RetrievedChunk(
        chunk_id=str(meta.get("id") or raw.get("location", {}).get("id") or ""),
        text=(raw.get("content", {}) or {}).get("text", ""),
        score=float(raw.get("score", 0.0) or 0.0),
        source_note_id=str(meta.get("source_note_id", "")),
        note_type=meta.get("note_type"),
        encounter_date=meta.get("encounter_date"),
        patient_scope=str(meta.get("patient_scope") or requested_scope),
    )


def kb_hybrid_retrieve(
    query: str,
    patient_scope: str,
    top_k: int = 10,
    *,
    client: Any = None,
    knowledge_base_id: str | None = None,
    region: str | None = None,
) -> list[RetrievedChunk]:
    """Hybrid retrieve scoped to ``patient_scope``. Out-of-scope rows are dropped
    defensively even though the KB filter should already exclude them."""
    kb_id = knowledge_base_id or os.environ.get("KNOWLEDGE_BASE_ID")
    if not kb_id:
        raise ValueError("knowledge_base_id or KNOWLEDGE_BASE_ID env is required")
    client = client or _client(region)

    resp = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration=build_retrieval_config(top_k, patient_scope),
    )
    chunks = [_to_chunk(r, patient_scope) for r in resp.get("retrievalResults", [])]
    return [c for c in chunks if c.patient_scope == patient_scope]
