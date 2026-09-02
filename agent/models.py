"""Shared data contracts for agent tools (SPEC.md §7 'Tool contracts').

Scaffold only — fields will firm up in Phase 4 when tools are implemented.
"""

from __future__ import annotations

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    source_note_id: str
    note_type: str | None = None
    encounter_date: str | None = None
    patient_scope: str


class OntologyMatch(BaseModel):
    entity_text: str
    code_system: str  # ICD10CM | SNOMEDCT | RXNORM
    code: str
    description: str | None = None
    confidence: float | None = None
    similarity: float | None = None


class FHIRBundle(BaseModel):
    resource_type: str = "Bundle"
    entry: list[dict] = []


class RerankedResult(BaseModel):
    index: int
    text: str
    relevance_score: float
