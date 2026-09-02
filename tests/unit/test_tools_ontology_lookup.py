"""Phase 4: ontology_lookup — pg_trgm SQL, allow-listed code systems, scope."""

from __future__ import annotations

import pytest

from agent.tools.ontology_lookup import ontology_lookup

ARNS = dict(resource_arn="arn:c", secret_arn="arn:s", database="clinical_rag")


class FakeRds:
    def __init__(self, records=None):
        self.records = records or []
        self.last = None

    def execute_statement(self, **kwargs):
        self.last = kwargs
        return {"records": self.records}


def _row(sim=0.5):
    return [
        {"stringValue": "contrast dye"},
        {"stringValue": "SNOMEDCT"},
        {"stringValue": "293637006"},
        {"stringValue": "Adverse reaction to contrast media"},
        {"doubleValue": 0.88},
        {"doubleValue": sim},
    ]


def test_sql_uses_trgm_operator_and_similarity_and_allowlisted_systems() -> None:
    fake = FakeRds([_row()])
    ontology_lookup("dye reaction", ["SNOMEDCT"], 3, client=fake, **ARNS)
    sql = fake.last["sql"]
    assert "similarity(entity_text, :term)" in sql
    assert "entity_text % :term" in sql
    assert "code_system IN ('SNOMEDCT')" in sql
    params = {p["name"]: p["value"] for p in fake.last["parameters"]}
    assert params["term"] == {"stringValue": "dye reaction"}
    assert params["top_k"] == {"longValue": 3}


def test_patient_scope_adds_bound_clause() -> None:
    fake = FakeRds([])
    ontology_lookup("x", client=fake, patient_scope="patient-001", **ARNS)
    assert "AND patient_scope = :scope" in fake.last["sql"]
    params = {p["name"]: p["value"] for p in fake.last["parameters"]}
    assert params["scope"] == {"stringValue": "patient-001"}


def test_rows_parsed_into_ontology_matches() -> None:
    fake = FakeRds([_row(sim=0.73)])
    out = ontology_lookup("dye", client=fake, **ARNS)
    assert out[0].code_system == "SNOMEDCT"
    assert out[0].code == "293637006"
    assert out[0].similarity == pytest.approx(0.73)
    assert out[0].confidence == pytest.approx(0.88)


def test_unknown_code_system_rejected() -> None:
    with pytest.raises(ValueError):
        ontology_lookup("x", ["LOINC"], client=FakeRds(), **ARNS)


def test_missing_aurora_arns_raise(monkeypatch) -> None:
    monkeypatch.delenv("AURORA_CLUSTER_ARN", raising=False)
    monkeypatch.delenv("AURORA_SECRET_ARN", raising=False)
    with pytest.raises(ValueError):
        ontology_lookup("x", client=FakeRds())
