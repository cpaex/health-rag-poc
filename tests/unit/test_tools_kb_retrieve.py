"""Phase 4: kb_hybrid_retrieve — HYBRID + scope filter, parsing, scope guard."""

from __future__ import annotations

import pytest

from agent.tools.kb_hybrid_retrieve import build_retrieval_config, kb_hybrid_retrieve


class FakeKB:
    def __init__(self, results):
        self.results = results
        self.last = None

    def retrieve(self, **kwargs):
        self.last = kwargs
        return {"retrievalResults": self.results}


def _hit(text, scope, score, note="note-001"):
    return {
        "content": {"text": text},
        "score": score,
        "metadata": {
            "patient_scope": scope,
            "source_note_id": note,
            "note_type": "x",
            "id": note + "#0",
        },
    }


def test_requests_hybrid_and_scope_filter() -> None:
    fake = FakeKB([_hit("a", "patient-001", 0.7)])
    kb_hybrid_retrieve("q", "patient-001", 4, client=fake, knowledge_base_id="KB123")
    cfg = fake.last["retrievalConfiguration"]["vectorSearchConfiguration"]
    assert fake.last["knowledgeBaseId"] == "KB123"
    assert cfg["overrideSearchType"] == "HYBRID"
    assert cfg["numberOfResults"] == 4
    assert cfg["filter"] == {"equals": {"key": "patient_scope", "value": "patient-001"}}


def test_parses_results_into_models() -> None:
    fake = FakeKB([_hit("chunk text", "patient-001", 0.42, "note-003")])
    out = kb_hybrid_retrieve("q", "patient-001", client=fake, knowledge_base_id="KB")
    assert out[0].text == "chunk text"
    assert out[0].score == pytest.approx(0.42)
    assert out[0].source_note_id == "note-003"
    assert out[0].patient_scope == "patient-001"


def test_drops_out_of_scope_rows_defensively() -> None:
    fake = FakeKB([_hit("mine", "patient-001", 0.9), _hit("theirs", "patient-002", 0.95)])
    out = kb_hybrid_retrieve("q", "patient-001", client=fake, knowledge_base_id="KB")
    assert [c.text for c in out] == ["mine"]


def test_missing_kb_id_raises() -> None:
    with pytest.raises(ValueError):
        kb_hybrid_retrieve("q", "patient-001", client=FakeKB([]))


def test_build_config_no_scope_has_no_filter() -> None:
    vsc = build_retrieval_config(3, None)["vectorSearchConfiguration"]
    assert "filter" not in vsc
