"""Phase 2: the KB Retrieve config must request HYBRID search and scope-filter."""

from __future__ import annotations

from agent.tools.kb_hybrid_retrieve import build_retrieval_config


def test_hybrid_search_always_requested() -> None:
    vsc = build_retrieval_config(top_k=5, patient_scope=None)["vectorSearchConfiguration"]
    assert vsc["overrideSearchType"] == "HYBRID"
    assert vsc["numberOfResults"] == 5
    assert "filter" not in vsc


def test_patient_scope_becomes_equals_filter() -> None:
    vsc = build_retrieval_config(top_k=3, patient_scope="patient-001")["vectorSearchConfiguration"]
    assert vsc["filter"] == {"equals": {"key": "patient_scope", "value": "patient-001"}}
