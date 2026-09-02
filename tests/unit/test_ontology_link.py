"""Phase 3: Infer* wrappers normalize three response shapes into ontology rows."""

from __future__ import annotations

from ingestion import ontology_link


class FakeCM:
    def __init__(self, icd=None, sct=None, rx=None) -> None:
        self._icd, self._sct, self._rx = icd or {}, sct or {}, rx or {}

    def infer_icd10_cm(self, Text: str) -> dict:  # noqa: N803
        return self._icd

    def infer_snomedct(self, Text: str) -> dict:  # noqa: N803
        return self._sct

    def infer_rx_norm(self, Text: str) -> dict:  # noqa: N803
        return self._rx


def test_infer_icd10cm_picks_highest_score_concept() -> None:
    fake = FakeCM(
        icd={
            "Entities": [
                {
                    "Text": "hypertension",
                    "Score": 0.97,
                    "ICD10CMConcepts": [
                        {"Code": "I10", "Description": "Essential hypertension", "Score": 0.91},
                        {"Code": "I15.9", "Description": "Secondary hypertension", "Score": 0.42},
                    ],
                }
            ]
        }
    )
    rows = ontology_link.infer_icd10cm("...", client=fake)
    assert rows == [
        {
            "entity_text": "hypertension",
            "code_system": "ICD10CM",
            "code": "I10",
            "description": "Essential hypertension",
            "confidence": 0.97,
        }
    ]


def test_entities_without_concepts_are_dropped() -> None:
    fake = FakeCM(sct={"Entities": [{"Text": "pain", "Score": 0.8, "SNOMEDCTConcepts": []}]})
    assert ontology_link.infer_snomedct("...", client=fake) == []


def test_link_all_merges_three_systems() -> None:
    fake = FakeCM(
        icd={
            "Entities": [
                {
                    "Text": "asthma",
                    "Score": 0.95,
                    "ICD10CMConcepts": [{"Code": "J45.40", "Description": "asthma", "Score": 0.9}],
                }
            ]
        },
        rx={
            "Entities": [
                {
                    "Text": "albuterol",
                    "Score": 0.99,
                    "RxNormConcepts": [{"Code": "435", "Description": "albuterol", "Score": 0.95}],
                }
            ]
        },
    )
    rows = ontology_link.link_all("...", client=fake)
    assert {r["code_system"] for r in rows} == {"ICD10CM", "RXNORM"}
