"""Titan V2 embeddings -> Aurora bedrock_integration.bedrock_kb (SPEC.md §6 step 5).

Sets custom_metadata.patient_scope for later access filtering. Writes via the RDS
Data API. Implemented in Phase 3.
"""

from __future__ import annotations


def embed(texts: list[str]) -> list[list[float]]:
    """Amazon Titan Text Embeddings V2 (1024-dim). Phase 3."""
    raise NotImplementedError("Phase 3: bedrock-runtime InvokeModel (titan-embed-text-v2)")


def load_chunks(chunks: list[dict]) -> int:
    """Insert embedded chunks into bedrock_integration.bedrock_kb. Phase 3."""
    raise NotImplementedError("Phase 3: RDS Data API batch insert")
