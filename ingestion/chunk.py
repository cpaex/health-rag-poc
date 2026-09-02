"""Section-aware chunking (SPEC.md §6 step 4).

Split on common clinical note headers (HPI, Assessment, Plan, Medications); fall
back to fixed-size chunks with overlap when headers aren't found. Implemented in
Phase 3.
"""

from __future__ import annotations

CLINICAL_HEADERS = ["HPI", "History of Present Illness", "Assessment", "Plan", "Medications"]


def chunk_note(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[dict]:
    raise NotImplementedError("Phase 3: section-aware chunking")
