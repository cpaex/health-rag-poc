"""Deterministic multi-step hybrid retrieval (SPEC.md §7, architecture doc Step 10).

resolve term -> broad semantic search -> notice a gap -> broaden and retrieve
again -> merge -> rerank -> return cited chunks.

This is the routine the supervisor delegates to for "needs ontology resolution
then semantic search" questions. It is pure Python over an injected ``tools``
object so it can be unit-tested with fakes and no Bedrock/DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from agent.models import OntologyMatch, RerankedResult, RetrievedChunk


class Tools(Protocol):
    def ontology_lookup(self, term: str, **kw: Any) -> list[OntologyMatch]: ...
    def kb_hybrid_retrieve(
        self, query: str, patient_scope: str, top_k: int = 10, **kw: Any
    ) -> list[RetrievedChunk]: ...
    def rerank(
        self, query: str, candidates: list[str], top_k: int, **kw: Any
    ) -> list[RerankedResult]: ...


@dataclass
class Step:
    tool: str
    args: dict
    result_count: int


@dataclass
class StrategyResult:
    chunks: list[RetrievedChunk]
    steps: list[Step] = field(default_factory=list)
    ontology: list[OntologyMatch] = field(default_factory=list)
    broadened: bool = False

    @property
    def tool_sequence(self) -> list[str]:
        return [s.tool for s in self.steps]


def _key(chunk: RetrievedChunk) -> str:
    return chunk.chunk_id or chunk.text[:120]


def hybrid_multistep(
    query: str,
    patient_scope: str,
    *,
    tools: Tools,
    top_k: int = 10,
    rerank_top_k: int = 5,
    min_hits: int = 2,
    weak_score: float = 0.35,
) -> StrategyResult:
    steps: list[Step] = []

    # 1. Resolve clinical terms in the question to ontology concepts.
    ontology = tools.ontology_lookup(query, patient_scope=patient_scope)
    steps.append(
        Step("ontology_lookup", {"term": query, "patient_scope": patient_scope}, len(ontology))
    )

    # 2. First-pass hybrid semantic search on the raw question.
    hits = tools.kb_hybrid_retrieve(query, patient_scope, top_k)
    steps.append(
        Step(
            "kb_hybrid_retrieve",
            {"query": query, "patient_scope": patient_scope, "top_k": top_k},
            len(hits),
        )
    )

    # 3. Notice a gap: too few hits, or the best hit is weak. Broaden the query
    #    with ontology descriptions/synonyms and retrieve again.
    best = max((c.score for c in hits), default=0.0)
    broadened = False
    if ontology and (len(hits) < min_hits or best < weak_score):
        expansion = " ".join(
            dict.fromkeys(  # de-dupe, keep order
                [m.entity_text for m in ontology] + [m.description or "" for m in ontology]
            )
        ).strip()
        broad_query = f"{query} {expansion}".strip()
        more = tools.kb_hybrid_retrieve(broad_query, patient_scope, top_k)
        steps.append(
            Step(
                "kb_hybrid_retrieve",
                {"query": broad_query, "patient_scope": patient_scope, "top_k": top_k},
                len(more),
            )
        )
        merged: dict[str, RetrievedChunk] = {_key(c): c for c in hits}
        for c in more:
            merged.setdefault(_key(c), c)
        hits = list(merged.values())
        broadened = True

    # 4. Rerank the merged candidate set; carry the rerank score back onto chunks.
    if hits:
        reranked = tools.rerank(query, [c.text for c in hits], rerank_top_k)
        steps.append(
            Step(
                "rerank",
                {"query": query, "candidates": len(hits), "top_k": rerank_top_k},
                len(reranked),
            )
        )
        if reranked:
            ordered: list[RetrievedChunk] = []
            for r in reranked:
                chunk = hits[r.index]
                chunk = chunk.model_copy(update={"score": r.relevance_score})
                ordered.append(chunk)
            hits = ordered

    return StrategyResult(chunks=hits, steps=steps, ontology=ontology, broadened=broadened)
