"""Phase 3: ontology_index insert — chunk_id/scope attached, nulls handled."""

from __future__ import annotations

from ingestion import ontology_index_load


class FakeRdsData:
    def __init__(self) -> None:
        self.statements: list[dict] = []

    def execute_statement(self, **kwargs) -> dict:
        self.statements.append(kwargs)
        return {}


def test_load_ontology_rows_binds_chunk_id_scope_and_nulls() -> None:
    fake = FakeRdsData()
    rows = [
        {
            "entity_text": "asthma",
            "code_system": "ICD10CM",
            "code": "J45.40",
            "description": "asthma",
            "confidence": 0.95,
        },
        {
            "entity_text": "cough",
            "code_system": "SNOMEDCT",
            "code": "49727002",
            "description": None,
            "confidence": None,
        },
    ]
    n = ontology_index_load.load_ontology_rows(
        rows,
        chunk_id="cid-1",
        patient_scope="patient-003",
        resource_arn="arn:c",
        secret_arn="arn:s",
        database="clinical_rag",
        client=fake,
    )
    assert n == 2
    p0 = {p["name"]: p["value"] for p in fake.statements[0]["parameters"]}
    assert p0["chunk_id"]["stringValue"] == "cid-1"
    assert p0["patient_scope"]["stringValue"] == "patient-003"
    assert p0["confidence"]["doubleValue"] == 0.95
    p1 = {p["name"]: p["value"] for p in fake.statements[1]["parameters"]}
    assert p1["description"] == {"isNull": True}
    assert p1["confidence"] == {"isNull": True}
    assert "CAST(:chunk_id AS uuid)" in fake.statements[0]["sql"]
