"""Comprehend Medical ontology linking (SPEC.md §6 step 3).

Wraps InferICD10CM / InferSNOMEDCT / InferRxNorm and normalizes the three
different response shapes into rows for the `ontology_index` table (§4):
``entity_text, code_system, code, description, confidence``.

AWS access is via an injectable client for unit testing.
"""

from __future__ import annotations

from typing import Any

CODE_SYSTEMS = ("ICD10CM", "SNOMEDCT", "RXNORM")
_MAX_BYTES = 10000  # Infer* limit is smaller than DetectPHI


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("comprehendmedical", region_name=region)


def _top_concept(entity: dict) -> tuple[str, str] | None:
    """Return (code, description) for the highest-score linked concept, or None."""
    concepts = (
        entity.get("ICD10CMConcepts")
        or entity.get("SNOMEDCTConcepts")
        or entity.get("RxNormConcepts")
        or []
    )
    if not concepts:
        return None
    best = max(concepts, key=lambda c: c.get("Score", 0.0))
    return str(best.get("Code", "")), best.get("Description")


def _rows_from_response(resp: dict, code_system: str) -> list[dict]:
    rows: list[dict] = []
    for ent in resp.get("Entities", []):
        concept = _top_concept(ent)
        if not concept:
            continue
        code, description = concept
        rows.append(
            {
                "entity_text": ent.get("Text", ""),
                "code_system": code_system,
                "code": code,
                "description": description,
                "confidence": ent.get("Score"),
            }
        )
    return rows


def _infer(
    api_method: str, code_system: str, text: str, client: Any, region: str | None
) -> list[dict]:
    client = client or _client(region)
    method = getattr(client, api_method)
    rows: list[dict] = []
    # Infer* has no offset rebasing need — we only keep entity text + codes.
    for piece in _byte_pieces(text, _MAX_BYTES):
        rows.extend(_rows_from_response(method(Text=piece), code_system))
    return rows


def infer_icd10cm(text: str, *, client: Any = None, region: str | None = None) -> list[dict]:
    return _infer("infer_icd10_cm", "ICD10CM", text, client, region)


def infer_snomedct(text: str, *, client: Any = None, region: str | None = None) -> list[dict]:
    return _infer("infer_snomedct", "SNOMEDCT", text, client, region)


def infer_rxnorm(text: str, *, client: Any = None, region: str | None = None) -> list[dict]:
    return _infer("infer_rx_norm", "RXNORM", text, client, region)


def link_all(text: str, *, client: Any = None, region: str | None = None) -> list[dict]:
    """Run all three inferrers and return unified ontology_index rows."""
    rows: list[dict] = []
    rows.extend(infer_icd10cm(text, client=client, region=region))
    rows.extend(infer_snomedct(text, client=client, region=region))
    rows.extend(infer_rxnorm(text, client=client, region=region))
    return rows


def _byte_pieces(text: str, max_bytes: int):
    if len(text.encode("utf-8")) <= max_bytes:
        yield text
        return
    start = 0
    while start < len(text):
        end, size = start, 0
        while end < len(text):
            n = len(text[end].encode("utf-8"))
            if size + n > max_bytes:
                break
            size += n
            end += 1
        yield text[start : max(end, start + 1)]
        start = max(end, start + 1)
