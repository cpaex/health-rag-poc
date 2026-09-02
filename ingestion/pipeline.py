"""End-to-end ingestion orchestrator (SPEC.md §6).

seed notes -> DetectPHI/redact -> section-aware chunk -> Titan V2 embed ->
load into bedrock_integration.bedrock_kb -> Infer* ontology link -> load
ontology_index. Called by scripts/seed_demo_data.sh.

`--dry-run` swaps every AWS client for a deterministic in-process fake so the
full wiring can be exercised with no credentials and no database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ingestion import deidentify, embed_and_load, ontology_index_load, ontology_link
from ingestion.chunk import chunk_note

DEFAULT_SEED_DIR = Path(__file__).resolve().parent / "seed_data"


@dataclass
class Note:
    source_note_id: str
    patient_scope: str
    patient_id: str
    note_type: str
    encounter_date: str
    text: str


@dataclass
class Summary:
    notes: int = 0
    chunks: int = 0
    kb_rows: list[str] = field(default_factory=list)
    ontology_rows: int = 0
    phi_spans: int = 0

    def as_dict(self) -> dict:
        return {
            "notes": self.notes,
            "chunks": self.chunks,
            "kb_rows": len(self.kb_rows),
            "ontology_rows": self.ontology_rows,
            "phi_spans": self.phi_spans,
        }


def load_notes(seed_dir: Path = DEFAULT_SEED_DIR) -> list[Note]:
    notes_dir = seed_dir / "notes"
    manifest = notes_dir / "manifest.jsonl"
    out: list[Note] = []
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        m = json.loads(line)
        out.append(
            Note(
                source_note_id=m["source_note_id"],
                patient_scope=m["patient_scope"],
                patient_id=m["patient_id"],
                note_type=m["note_type"],
                encounter_date=m["encounter_date"],
                text=(notes_dir / m["file"]).read_text(),
            )
        )
    return out


def run(
    seed_dir: Path = DEFAULT_SEED_DIR,
    *,
    resource_arn: str,
    secret_arn: str,
    database: str,
    region: str | None = None,
    cm_client: Any = None,
    bedrock_client: Any = None,
    rds_client: Any = None,
) -> Summary:
    summary = Summary()
    for note in load_notes(seed_dir):
        summary.notes += 1

        phi = deidentify.detect_phi(note.text, client=cm_client, region=region)
        summary.phi_spans += len(phi)
        clean = deidentify.redact(note.text, phi)

        chunks = chunk_note(clean)
        summary.chunks += len(chunks)
        if not chunks:
            continue

        vectors = embed_and_load.embed(
            [c["text"] for c in chunks], client=bedrock_client, region=region
        )

        kb_rows = [
            {
                "text": c["text"],
                "embedding": vec,
                "metadata": {
                    "source": note.source_note_id,
                    "AMAZON_BEDROCK_TEXT": c["text"],
                },
                "custom_metadata": {
                    "patient_scope": note.patient_scope,
                    "source_note_id": note.source_note_id,
                    "note_type": note.note_type,
                    "encounter_date": note.encounter_date,
                    "section": c["section"],
                },
            }
            for c, vec in zip(chunks, vectors, strict=True)
        ]
        ids = embed_and_load.load_chunks(
            kb_rows,
            resource_arn=resource_arn,
            secret_arn=secret_arn,
            database=database,
            client=rds_client,
            region=region,
        )
        summary.kb_rows.extend(ids)

        for chunk, chunk_id in zip(chunks, ids, strict=True):
            ont_rows = ontology_link.link_all(chunk["text"], client=cm_client, region=region)
            if not ont_rows:
                continue
            summary.ontology_rows += ontology_index_load.load_ontology_rows(
                ont_rows,
                chunk_id=chunk_id,
                patient_scope=note.patient_scope,
                resource_arn=resource_arn,
                secret_arn=secret_arn,
                database=database,
                client=rds_client,
                region=region,
            )
    return summary


# --------------------------------------------------------------------------- #
# Dry-run fakes                                                                #
# --------------------------------------------------------------------------- #
class _DryComprehendMedical:
    def detect_phi(self, Text: str) -> dict:  # noqa: N803 (boto3 kwarg name)
        return {"Entities": []}

    def _infer(self, Text: str) -> dict:  # noqa: N803
        return {"Entities": []}

    infer_icd10_cm = _infer
    infer_snomedct = _infer
    infer_rx_norm = _infer


class _DryBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _DryBedrock:
    def invoke_model(self, modelId: str, body: str) -> dict:  # noqa: N803
        payload = json.dumps({"embedding": [0.0] * embed_and_load.EMBED_DIM}).encode()
        return {"body": _DryBody(payload)}


class _DryRdsData:
    def execute_statement(self, **kwargs: Any) -> dict:
        return {"records": [[{"stringValue": str(uuid.uuid4())}]]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    ap.add_argument("--dry-run", action="store_true", help="no AWS, no DB — wiring check only")
    ap.add_argument("--resource-arn", default=os.environ.get("AURORA_CLUSTER_ARN"))
    ap.add_argument("--secret-arn", default=os.environ.get("AURORA_SECRET_ARN"))
    ap.add_argument("--database", default=os.environ.get("AURORA_DATABASE_NAME", "clinical_rag"))
    ap.add_argument("--region", default=os.environ.get("AWS_REGION"))
    args = ap.parse_args(argv)

    kwargs: dict[str, Any] = {}
    if args.dry_run:
        kwargs = {
            "cm_client": _DryComprehendMedical(),
            "bedrock_client": _DryBedrock(),
            "rds_client": _DryRdsData(),
            "resource_arn": "dry-run",
            "secret_arn": "dry-run",
            "database": args.database,
        }
    else:
        if not args.resource_arn or not args.secret_arn:
            print("error: --resource-arn/--secret-arn (or AURORA_* env) required", file=sys.stderr)
            return 2
        kwargs = {
            "resource_arn": args.resource_arn,
            "secret_arn": args.secret_arn,
            "database": args.database,
            "region": args.region,
        }

    summary = run(args.seed_dir, **kwargs)
    print(json.dumps(summary.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
