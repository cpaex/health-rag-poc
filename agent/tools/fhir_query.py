"""Structured lookup against the mocked FHIR endpoint.

Non-goal (SPEC.md §2): no real Epic/HealthLake connection. This calls a local
FastAPI/static-JSON responder at MOCK_FHIR_ENDPOINT_URL that returns HealthLake-shaped
data. Extension point for real HealthLake is marked here. Implemented in Phase 4.
"""

from __future__ import annotations

from agent.models import FHIRBundle


def fhir_query(patient_id: str, resource_type: str, params: dict) -> FHIRBundle:
    raise NotImplementedError("Phase 4: call MOCK_FHIR_ENDPOINT_URL")
