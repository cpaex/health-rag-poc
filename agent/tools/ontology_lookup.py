"""Fuzzy/exact search over ontology_index using pg_trgm similarity.

Implemented in Phase 4. Runs against Aurora via the RDS Data API.
"""

from __future__ import annotations

from agent.models import OntologyMatch

DEFAULT_CODE_SYSTEMS = ["ICD10CM", "SNOMEDCT", "RXNORM"]


def ontology_lookup(
    term: str,
    code_systems: list[str] | None = None,
    top_k: int = 5,
) -> list[OntologyMatch]:
    code_systems = code_systems or DEFAULT_CODE_SYSTEMS
    raise NotImplementedError("Phase 4: pg_trgm similarity query over ontology_index")
