"""Phase 2: the KB Retrieve config must request HYBRID search and scope-filter."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "kb_smoke_test", Path(__file__).resolve().parents[2] / "scripts" / "kb_smoke_test.py"
)
kb_smoke_test = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb_smoke_test)


def test_hybrid_search_always_requested() -> None:
    cfg = kb_smoke_test.build_retrieval_config(top_k=5, patient_scope=None)
    vsc = cfg["vectorSearchConfiguration"]
    assert vsc["overrideSearchType"] == "HYBRID"
    assert vsc["numberOfResults"] == 5
    assert "filter" not in vsc


def test_patient_scope_becomes_equals_filter() -> None:
    cfg = kb_smoke_test.build_retrieval_config(top_k=3, patient_scope="patient-001")
    vsc = cfg["vectorSearchConfiguration"]
    assert vsc["filter"] == {"equals": {"key": "patient_scope", "value": "patient-001"}}
