"""Structured lookup against the mocked FHIR endpoint (SPEC.md §7, §2 non-goal).

No real Epic/HealthLake. Hits a local responder at ``MOCK_FHIR_ENDPOINT_URL``
that returns HealthLake-shaped Bundles (see ``mocks/fhir_server.py``).

EXTENSION POINT: swap the HTTP call for a HealthLake FHIR datastore request
(``healthlake`` / the datastore's FHIR REST endpoint with SigV4). Keep this
function signature — the supervisor depends on it.
"""

from __future__ import annotations

import os
from typing import Any

from agent.models import FHIRBundle


def _http(base_url: str) -> Any:
    import httpx

    return httpx.Client(base_url=base_url, timeout=10.0)


def fhir_query(
    patient_id: str,
    resource_type: str,
    params: dict,
    *,
    base_url: str | None = None,
    client: Any = None,
) -> FHIRBundle:
    base_url = base_url or os.environ.get("MOCK_FHIR_ENDPOINT_URL", "http://localhost:8000")
    query = {"patient": patient_id, **(params or {})}

    owns_client = client is None
    client = client or _http(base_url)
    try:
        resp = client.get(f"/{resource_type}", params=query)
        resp.raise_for_status()
        body = resp.json()
    finally:
        if owns_client and hasattr(client, "close"):
            client.close()

    return FHIRBundle(
        resource_type=body.get("resourceType", "Bundle"),
        entry=body.get("entry", []),
    )
