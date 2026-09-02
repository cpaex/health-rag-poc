"""Phase 4: the multi-step retrieval strategy (architecture doc Step 10).

resolve term -> search -> notice gap -> broaden -> retrieve again -> rerank.
Every AWS-backed tool is faked; we assert the tool-call *sequence* and the
broaden decision, including the seed data's contrast-dye scenario.
"""

from __future__ import annotations

from agent.models import OntologyMatch, RerankedResult, RetrievedChunk
from agent.retrieval_strategy import hybrid_multistep


def chunk(text, score, note="note-001", scope="patient-001"):
    return RetrievedChunk(
        chunk_id=f"{note}#{abs(hash(text)) % 100}",
        text=text,
        score=score,
        source_note_id=note,
        patient_scope=scope,
    )


class FakeTools:
    def __init__(self, *, ontology, kb_batches, rerank_order):
        self._ontology = ontology
        self._kb_batches = list(kb_batches)  # one list per kb_hybrid_retrieve call
        self._rerank_order = rerank_order
        self.kb_queries: list[str] = []

    def ontology_lookup(self, term, **kw):
        return list(self._ontology)

    def kb_hybrid_retrieve(self, query, patient_scope, top_k=10, **kw):
        self.kb_queries.append(query)
        return self._kb_batches.pop(0) if self._kb_batches else []

    def rerank(self, query, candidates, top_k, **kw):
        # rerank_order is a list of indices into `candidates`
        return [
            RerankedResult(index=i, text=candidates[i], relevance_score=1.0 - n * 0.1)
            for n, i in enumerate(self._rerank_order)
            if i < len(candidates)
        ][:top_k]


def test_strong_first_hit_does_not_broaden() -> None:
    tools = FakeTools(
        ontology=[
            OntologyMatch(entity_text="contrast media reaction", code_system="SNOMEDCT", code="1")
        ],
        kb_batches=[[chunk("a", 0.81), chunk("b", 0.6), chunk("c", 0.55)]],
        rerank_order=[2, 0, 1],
    )
    res = hybrid_multistep("q", "patient-001", tools=tools, min_hits=2, weak_score=0.35)
    assert res.tool_sequence == ["ontology_lookup", "kb_hybrid_retrieve", "rerank"]
    assert res.broadened is False
    assert [c.text for c in res.chunks] == ["c", "a", "b"]  # rerank order applied


def test_contrast_dye_scenario_broadens_then_reranks() -> None:
    ontology = [
        OntologyMatch(
            entity_text="contrast dye",
            code_system="SNOMEDCT",
            code="293637006",
            description="Adverse reaction to contrast media",
        )
    ]
    tools = FakeTools(
        ontology=ontology,
        kb_batches=[
            [chunk("weak lone hit", 0.18)],  # 1st pass: 1 weak hit -> gap
            [
                chunk("blotchy and tight in the throat", 0.7, "note-001"),
                chunk("hives after the dye study", 0.66, "note-003"),
                chunk("premedication for future iodinated contrast", 0.6, "note-010"),
            ],
        ],
        rerank_order=[1, 2, 3, 0],
    )
    res = hybrid_multistep(
        "did she react to the dye?",
        "patient-001",
        tools=tools,
        min_hits=2,
        weak_score=0.35,
        rerank_top_k=3,
    )

    assert res.tool_sequence == [
        "ontology_lookup",
        "kb_hybrid_retrieve",
        "kb_hybrid_retrieve",
        "rerank",
    ]
    assert res.broadened is True
    # the broadened query carries the ontology expansion
    assert "contrast dye" in tools.kb_queries[1]
    assert "Adverse reaction to contrast media" in tools.kb_queries[1]
    # merged set (1 + 3) reranked, all in-scope, rerank score carried onto chunk
    assert len(res.chunks) == 3
    assert all(c.patient_scope == "patient-001" for c in res.chunks)
    assert res.chunks[0].score == 1.0


def test_no_ontology_match_cannot_broaden() -> None:
    tools = FakeTools(
        ontology=[],
        kb_batches=[[chunk("only weak", 0.1)]],
        rerank_order=[0],
    )
    res = hybrid_multistep("q", "patient-001", tools=tools, min_hits=2)
    assert res.tool_sequence == ["ontology_lookup", "kb_hybrid_retrieve", "rerank"]
    assert res.broadened is False


def test_no_hits_skips_rerank() -> None:
    tools = FakeTools(ontology=[], kb_batches=[[]], rerank_order=[])
    res = hybrid_multistep("q", "patient-001", tools=tools)
    assert res.tool_sequence == ["ontology_lookup", "kb_hybrid_retrieve"]
    assert res.chunks == []
