"""Phase 3: end-to-end pipeline wiring with every AWS client faked."""

from __future__ import annotations

import json
import uuid

from ingestion import pipeline


class FakeCM:
    def detect_phi(self, Text):  # noqa: N803
        # one PHI span so the redact path is exercised
        idx = Text.find("MRN-")
        ents = []
        if idx != -1:
            ents.append(
                {
                    "Type": "ID",
                    "Text": Text[idx : idx + 11],
                    "BeginOffset": idx,
                    "EndOffset": idx + 11,
                }
            )
        return {"Entities": ents}

    def infer_icd10_cm(self, Text):  # noqa: N803
        if "asthma" in Text.lower():
            return {
                "Entities": [
                    {
                        "Text": "asthma",
                        "Score": 0.9,
                        "ICD10CMConcepts": [
                            {"Code": "J45.40", "Description": "asthma", "Score": 0.9}
                        ],
                    }
                ]
            }
        return {"Entities": []}

    def infer_snomedct(self, Text):  # noqa: N803
        return {"Entities": []}

    def infer_rx_norm(self, Text):  # noqa: N803
        return {"Entities": []}


class FakeBody:
    def __init__(self, p):
        self._p = p

    def read(self):
        return self._p


class FakeBedrock:
    def invoke_model(self, modelId, body):  # noqa: N803
        return {
            "body": FakeBody(
                json.dumps({"embedding": [0.0] * pipeline.embed_and_load.EMBED_DIM}).encode()
            )
        }


class FakeRds:
    def __init__(self):
        self.inserts = []

    def execute_statement(self, **kw):
        self.inserts.append(kw)
        if "RETURNING id" in kw["sql"]:
            return {"records": [[{"stringValue": str(uuid.uuid4())}]]}
        return {}


def test_run_processes_all_seed_notes_end_to_end() -> None:
    rds = FakeRds()
    summary = pipeline.run(
        resource_arn="arn:c",
        secret_arn="arn:s",
        database="clinical_rag",
        cm_client=FakeCM(),
        bedrock_client=FakeBedrock(),
        rds_client=rds,
    )
    assert summary.notes == 10
    assert summary.chunks >= summary.notes
    assert len(summary.kb_rows) == summary.chunks
    assert summary.phi_spans >= 10  # every note has an MRN
    assert summary.ontology_rows >= 1  # asthma notes link at least one code
    kb_inserts = [i for i in rds.inserts if "bedrock_kb" in i["sql"]]
    assert len(kb_inserts) == summary.chunks
    scopes = {
        json.loads(
            {p["name"]: p["value"] for p in i["parameters"]}["custom_metadata"]["stringValue"]
        )["patient_scope"]
        for i in kb_inserts
    }
    assert scopes == {"patient-001", "patient-002", "patient-003"}


def test_main_dry_run_needs_no_aws(capsys) -> None:
    rc = pipeline.main(["--dry-run"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["notes"] == 10
    assert out["kb_rows"] == out["chunks"]
