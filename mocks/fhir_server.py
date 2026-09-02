"""Minimal mocked FHIR R4 endpoint (SPEC.md §2 non-goal: no real Epic/HealthLake).

Serves the synthetic Bundles in ``ingestion/seed_data/fhir/`` as searchset
Bundles shaped like a HealthLake FHIR datastore response. Supports:

  GET /{ResourceType}?patient={id}[&code=...&status=...]
  GET /Patient?_id={id}
  GET /metadata            -> tiny CapabilityStatement
  GET /healthz

Run: ``uvicorn mocks.fhir_server:app --port 8000``  (or scripts/run_mock_fhir.sh)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request

_FHIR_DIR = Path(__file__).resolve().parents[1] / "ingestion" / "seed_data" / "fhir"

app = FastAPI(title="Mock FHIR (synthetic)", version="0.1.0")


@lru_cache(maxsize=1)
def _resources() -> list[dict]:
    out: list[dict] = []
    for path in sorted(_FHIR_DIR.glob("*.json")):
        bundle = json.loads(path.read_text())
        for entry in bundle.get("entry", []):
            res = entry.get("resource")
            if res:
                out.append(res)
    return out


def _patient_ref(res: dict) -> str | None:
    if res.get("resourceType") == "Patient":
        return res.get("id")
    ref = (res.get("subject") or res.get("patient") or {}).get("reference", "")
    return ref.split("/", 1)[1] if "/" in ref else (ref or None)


def _matches_filters(res: dict, query: dict) -> bool:
    reserved = {"patient", "_id", "_count"}
    for key, want in query.items():
        if key in reserved:
            continue
        if key == "code":
            codes = {c.get("code") for c in (res.get("code", {}).get("coding") or [])}
            if want not in codes:
                return False
        elif res.get(key) != want:
            return False
    return True


def _searchset(resources: list[dict]) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resources),
        "entry": [{"resource": r} for r in resources],
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "resources": len(_resources())}


@app.get("/metadata")
def metadata() -> dict:
    return {"resourceType": "CapabilityStatement", "status": "active", "fhirVersion": "4.0.1"}


@app.get("/{resource_type}")
def search(resource_type: str, request: Request) -> dict:
    query = dict(request.query_params)
    patient = query.get("patient") or query.get("_id")
    hits = [
        r
        for r in _resources()
        if r.get("resourceType") == resource_type
        and (patient is None or _patient_ref(r) == patient)
        and _matches_filters(r, query)
    ]
    return _searchset(hits)
