"""Bedrock Rerank API call using Cohere Rerank 3.5 (SPEC.md §7).

Uses ``bedrock-agent-runtime:Rerank`` with an inline TEXT source per candidate.
Verified request shape against the boto3 ``bedrock-agent-runtime`` reference
(2026-09): ``queries=[{type: TEXT, textQuery}]``,
``sources=[{type: INLINE, inlineDocumentSource: {type: TEXT, textDocument}}]``,
``rerankingConfiguration.bedrockRerankingConfiguration.modelConfiguration.modelArn``.
"""

from __future__ import annotations

import os
from typing import Any

from agent.models import RerankedResult

DEFAULT_MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("bedrock-agent-runtime", region_name=region)


def rerank(
    query: str,
    candidates: list[str],
    top_k: int,
    *,
    client: Any = None,
    model_arn: str | None = None,
    region: str | None = None,
) -> list[RerankedResult]:
    if not candidates:
        return []
    model_arn = model_arn or os.environ.get("RERANK_MODEL_ARN") or DEFAULT_MODEL_ARN
    client = client or _client(region)
    n = min(top_k, len(candidates))

    resp = client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": query}}],
        sources=[
            {
                "type": "INLINE",
                "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": c}},
            }
            for c in candidates
        ],
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "modelConfiguration": {"modelArn": model_arn},
                "numberOfResults": n,
            },
        },
    )

    out: list[RerankedResult] = []
    for r in resp.get("results", []):
        idx = int(r["index"])
        out.append(
            RerankedResult(
                index=idx,
                text=candidates[idx],
                relevance_score=float(r.get("relevanceScore", 0.0)),
            )
        )
    return out
