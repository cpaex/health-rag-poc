"""Phase 4: supervisor assembly (no model call) + system-prompt rules present."""

from __future__ import annotations

from agent import supervisor


class FakeModel:
    stateful = False

    def get_config(self):
        return {}


def test_build_tools_exposes_the_five_capabilities() -> None:
    tools = supervisor.build_tools(supervisor.SupervisorConfig())
    assert sorted(t.tool_name for t in tools) == sorted(supervisor.TOOL_NAMES)


def test_build_supervisor_registers_tools_without_touching_bedrock() -> None:
    agent = supervisor.build_supervisor(model=FakeModel())
    registered = set(agent.tool_registry.registry)
    assert registered == set(supervisor.TOOL_NAMES)


def test_multi_step_tool_runs_the_strategy_over_bound_calls(monkeypatch) -> None:
    calls = {"ontology": 0, "kb": 0, "rerank": 0}

    import agent.supervisor as s

    def fake_bound(config):
        def ontology_lookup(term, code_systems=None, top_k=5, **kw):
            calls["ontology"] += 1
            from agent.models import OntologyMatch

            return [
                OntologyMatch(
                    entity_text="dye",
                    code_system="SNOMEDCT",
                    code="1",
                    description="Adverse reaction to contrast media",
                )
            ]

        def kb_hybrid_retrieve(query, patient_scope, top_k=10, **kw):
            calls["kb"] += 1
            from agent.models import RetrievedChunk

            score = 0.1 if calls["kb"] == 1 else 0.7
            return [
                RetrievedChunk(
                    chunk_id=f"c{calls['kb']}",
                    text="t",
                    score=score,
                    source_note_id="note-001",
                    patient_scope=patient_scope,
                )
            ]

        def rerank(query, candidates, top_k, **kw):
            calls["rerank"] += 1
            from agent.models import RerankedResult

            return [RerankedResult(index=0, text=candidates[0], relevance_score=0.9)]

        def fhir_query(*a, **k):  # unused here
            raise AssertionError

        return {
            "ontology_lookup": ontology_lookup,
            "kb_hybrid_retrieve": kb_hybrid_retrieve,
            "rerank": rerank,
            "fhir_query": fhir_query,
        }

    monkeypatch.setattr(s, "bound_callables", fake_bound)
    tools = {t.tool_name: t for t in s.build_tools(s.SupervisorConfig())}
    out = tools["multi_step_retrieve"]("did she react to the dye?", "patient-001")

    assert out["broadened"] is True
    assert out["tool_sequence"] == [
        "ontology_lookup",
        "kb_hybrid_retrieve",
        "kb_hybrid_retrieve",
        "rerank",
    ]
    assert calls == {"ontology": 1, "kb": 2, "rerank": 1}


def test_system_prompt_has_the_five_rules() -> None:
    text = supervisor.load_system_prompt().lower()
    for needle in [
        "cited",
        "source note id",
        "retrieval returns nothing",
        "decision support",
        "patient scope",
    ]:
        assert needle in text
