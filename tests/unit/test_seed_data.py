"""Phase 3: the synthetic seed data is well-formed and demo-meaningful."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SEED = Path(__file__).resolve().parents[2] / "ingestion" / "seed_data"
FHIR = SEED / "fhir"
NOTES = SEED / "notes"


def _manifest() -> list[dict]:
    return [
        json.loads(ln) for ln in (NOTES / "manifest.jsonl").read_text().splitlines() if ln.strip()
    ]


def test_between_8_and_12_notes_all_present() -> None:
    rows = _manifest()
    assert 8 <= len(rows) <= 12
    for r in rows:
        assert (NOTES / r["file"]).is_file()
        assert (NOTES / r["file"]).read_text().strip()


def test_manifest_fields_and_scopes() -> None:
    required = {
        "file",
        "source_note_id",
        "patient_scope",
        "patient_id",
        "note_type",
        "encounter_date",
    }
    scopes = set()
    for r in _manifest():
        assert required <= r.keys()
        scopes.add(r["patient_scope"])
    assert scopes == {"patient-001", "patient-002", "patient-003"}


def test_at_least_one_headerless_note_for_fallback_chunking() -> None:
    assert any(r.get("has_headers") is False for r in _manifest())


def test_contrast_dye_multistep_case_exists_with_unusual_phrasing() -> None:
    texts = {r["file"]: (NOTES / r["file"]).read_text().lower() for r in _manifest()}
    joined = " ".join(texts.values())
    assert "contrast" in joined
    # The reaction is introduced with indirect phrasing, not the words
    # "allergy"/"anaphylaxis", so a naive keyword search misses it — that is
    # what makes the multi-step retrieval demo meaningful.
    assert "blotchy and tight in the throat" in texts["note-001.txt"]
    # ...and the connection is spread across more than one note for that patient.
    p1_notes = [f for f, t in texts.items() if "contrast" in t or "dye" in t]
    assert len(p1_notes) >= 2


@pytest.mark.parametrize("path", sorted(FHIR.glob("*.json")))
def test_fhir_bundles_valid_and_have_core_resource_types(path: Path) -> None:
    bundle = json.loads(path.read_text())
    assert bundle["resourceType"] == "Bundle"
    types = {e["resource"]["resourceType"] for e in bundle["entry"]}
    assert {"Patient", "Condition", "Observation", "MedicationRequest"} <= types


def test_three_patient_bundles() -> None:
    assert len(list(FHIR.glob("*.json"))) == 3
