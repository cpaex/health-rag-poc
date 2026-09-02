"""Writes the `ontology_index` table (SPEC.md §4, §6 step 3).

Takes unified rows from ontology_link.link_all(), attaches chunk_id + patient_scope,
inserts via the RDS Data API. Implemented in Phase 3.
"""

from __future__ import annotations


def load_ontology_rows(rows: list[dict]) -> int:
    raise NotImplementedError("Phase 3: RDS Data API insert into ontology_index")
