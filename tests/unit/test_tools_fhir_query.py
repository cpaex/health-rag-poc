"""Phase 4: fhir_query — request path/params + parsing, against a fake and the
real mock FHIR server."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent.tools.fhir_query import fhir_query
from mocks.fhir_server import app


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return FakeResp(self.payload)


def test_builds_patient_scoped_request() -> None:
    fake = FakeHttp({"resourceType": "Bundle", "entry": []})
    fhir_query("patient-002", "MedicationRequest", {"status": "active"}, client=fake)
    path, params = fake.calls[0]
    assert path == "/MedicationRequest"
    assert params == {"patient": "patient-002", "status": "active"}


def test_parses_bundle_entries() -> None:
    fake = FakeHttp(
        {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Condition"}}]}
    )
    bundle = fhir_query("patient-001", "Condition", {}, client=fake)
    assert bundle.resource_type == "Bundle"
    assert bundle.entry[0]["resource"]["resourceType"] == "Condition"


def test_against_real_mock_server_filters_by_patient_and_code() -> None:
    client = TestClient(app)

    all_conditions = fhir_query("patient-001", "Condition", {}, client=client)
    assert len(all_conditions.entry) == 2  # HTN + T2DM from patient-001.json
    assert all(
        e["resource"]["subject"]["reference"] == "Patient/patient-001" for e in all_conditions.entry
    )

    htn = fhir_query("patient-001", "Condition", {"code": "I10"}, client=client)
    assert len(htn.entry) == 1

    other = fhir_query("patient-003", "MedicationRequest", {}, client=client)
    assert {e["resource"]["resourceType"] for e in other.entry} == {"MedicationRequest"}
