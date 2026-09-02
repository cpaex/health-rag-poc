"""Writes the `ontology_index` table (SPEC.md §4, §6 step 3).

Takes unified rows from `ontology_link.link_all()`, attaches the owning
`chunk_id` and the mirrored `patient_scope`, and inserts them over the RDS Data
API. Injectable client for unit testing.
"""

from __future__ import annotations

from typing import Any

_INSERT_SQL = (
    "INSERT INTO ontology_index "
    "(chunk_id, entity_text, code_system, code, description, confidence, patient_scope) "
    "VALUES (CAST(:chunk_id AS uuid), :entity_text, :code_system, :code, "
    ":description, :confidence, :patient_scope)"
)


def _rds_data(region: str | None = None) -> Any:
    import boto3

    return boto3.client("rds-data", region_name=region)


def load_ontology_rows(
    rows: list[dict],
    *,
    chunk_id: str,
    patient_scope: str,
    resource_arn: str,
    secret_arn: str,
    database: str,
    client: Any = None,
    region: str | None = None,
) -> int:
    """Insert ontology rows for one chunk. Returns the count inserted."""
    client = client or _rds_data(region)
    inserted = 0
    for row in rows:
        conf = row.get("confidence")
        params = [
            {"name": "chunk_id", "value": {"stringValue": chunk_id}},
            {"name": "entity_text", "value": {"stringValue": row["entity_text"]}},
            {"name": "code_system", "value": {"stringValue": row["code_system"]}},
            {"name": "code", "value": {"stringValue": str(row["code"])}},
            _nullable("description", row.get("description")),
            {
                "name": "confidence",
                "value": {"isNull": True} if conf is None else {"doubleValue": float(conf)},
            },
            {"name": "patient_scope", "value": {"stringValue": patient_scope}},
        ]
        client.execute_statement(
            resourceArn=resource_arn,
            secretArn=secret_arn,
            database=database,
            sql=_INSERT_SQL,
            parameters=params,
        )
        inserted += 1
    return inserted


def _nullable(name: str, value: str | None) -> dict:
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    return {"name": name, "value": {"stringValue": value}}
