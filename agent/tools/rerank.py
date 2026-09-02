"""Bedrock Rerank API call using Cohere Rerank 3.5.

Implemented in Phase 4. Uses bedrock-agent-runtime `Rerank` (or `bedrock` `Rerank`,
verify at build time) with RERANK_MODEL_ARN.
"""

from __future__ import annotations

from agent.models import RerankedResult


def rerank(query: str, candidates: list[str], top_k: int) -> list[RerankedResult]:
    raise NotImplementedError("Phase 4: Bedrock Rerank API (cohere.rerank-v3-5)")
