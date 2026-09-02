"""Titan V2 embeddings -> Aurora bedrock_integration.bedrock_kb (SPEC.md §6 step 5).

`embed()` calls Amazon Titan Text Embeddings V2 via bedrock-runtime.
`load_chunks()` inserts rows into the §4 KB table over the RDS Data API and
returns the generated row ids (needed to link `ontology_index.chunk_id`).

All AWS access is via injectable clients for unit testing.
"""

from __future__ import annotations

import json
from typing import Any

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM = 1024
_KB_TABLE = "bedrock_integration.bedrock_kb"

_INSERT_SQL = (
    f"INSERT INTO {_KB_TABLE} (embedding, chunks, metadata, custom_metadata) "
    "VALUES (CAST(:embedding AS vector), :chunks, CAST(:metadata AS jsonb), "
    "CAST(:custom_metadata AS jsonb)) RETURNING id"
)


def _bedrock(region: str | None = None) -> Any:
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


def _rds_data(region: str | None = None) -> Any:
    import boto3

    return boto3.client("rds-data", region_name=region)


def embed(
    texts: list[str],
    *,
    client: Any = None,
    model_id: str = TITAN_MODEL_ID,
    dimensions: int = EMBED_DIM,
    region: str | None = None,
) -> list[list[float]]:
    """Return one 1024-d embedding per input string (Titan V2, normalized)."""
    client = client or _bedrock(region)
    out: list[list[float]] = []
    for text in texts:
        body = json.dumps({"inputText": text, "dimensions": dimensions, "normalize": True})
        resp = client.invoke_model(modelId=model_id, body=body)
        payload = resp["body"].read() if hasattr(resp["body"], "read") else resp["body"]
        out.append(json.loads(payload)["embedding"])
    return out


def load_chunks(
    rows: list[dict],
    *,
    resource_arn: str,
    secret_arn: str,
    database: str,
    client: Any = None,
    region: str | None = None,
) -> list[str]:
    """Insert KB rows and return their generated ids, in input order.

    Each row: ``{"text": str, "embedding": list[float], "metadata": dict,
    "custom_metadata": dict}``. ``custom_metadata`` must carry ``patient_scope``
    (SPEC.md §6 step 5) plus ``source_note_id`` / ``note_type`` /
    ``encounter_date`` for filtering.
    """
    client = client or _rds_data(region)
    ids: list[str] = []
    for row in rows:
        params = [
            {"name": "embedding", "value": {"stringValue": _vec_literal(row["embedding"])}},
            {"name": "chunks", "value": {"stringValue": row["text"]}},
            {"name": "metadata", "value": {"stringValue": json.dumps(row.get("metadata", {}))}},
            {
                "name": "custom_metadata",
                "value": {"stringValue": json.dumps(row.get("custom_metadata", {}))},
            },
        ]
        resp = client.execute_statement(
            resourceArn=resource_arn,
            secretArn=secret_arn,
            database=database,
            sql=_INSERT_SQL,
            parameters=params,
        )
        ids.append(_first_string(resp))
    return ids


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _first_string(resp: dict) -> str:
    records = resp.get("records") or []
    return records[0][0]["stringValue"]
