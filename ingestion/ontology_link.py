"""Comprehend Medical ontology linking (SPEC.md §6 step 3).

Wraps InferICD10CM / InferSNOMEDCT / InferRxNorm and returns normalized rows for
the `ontology_index` table. Implemented in Phase 3.
"""

from __future__ import annotations


def infer_icd10cm(text: str) -> list[dict]:
    raise NotImplementedError("Phase 3: comprehendmedical.infer_icd10_cm")


def infer_snomedct(text: str) -> list[dict]:
    raise NotImplementedError("Phase 3: comprehendmedical.infer_snomed_ct")


def infer_rxnorm(text: str) -> list[dict]:
    raise NotImplementedError("Phase 3: comprehendmedical.infer_rx_norm")


def link_all(text: str) -> list[dict]:
    """Run all three inferrers, return unified rows for ontology_index. Phase 3."""
    raise NotImplementedError("Phase 3")
