"""Comprehend Medical DetectPHI wrapper (SPEC.md §6 step 2).

Runs for real against `comprehendmedical:DetectPHI` even on synthetic seed data, so
the code path is exercised and demonstrably correct. Implemented in Phase 3.
"""

from __future__ import annotations


def detect_phi(text: str) -> list[dict]:
    """Return Comprehend Medical PHI entities for `text`. Phase 3."""
    raise NotImplementedError("Phase 3: comprehendmedical.detect_phi")


def redact(text: str, entities: list[dict]) -> str:
    """Replace detected PHI spans with typed placeholders. Phase 3."""
    raise NotImplementedError("Phase 3")
