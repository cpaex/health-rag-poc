"""Fuzzy/exact search over ontology_index using pg_trgm similarity (SPEC.md §7).

Runs against Aurora via the RDS Data API. ``patient_scope`` is an optional
keyword (not in the SPEC tool contract signature) so the supervisor can keep
ontology results inside the authorized scope, mirroring the KB filter.
"""

from __future__ import annotations

import os
from typing import Any

from agent.models import OntologyMatch

CODE_SYSTEMS = ("ICD10CM", "SNOMEDCT", "RXNORM")

_SQL = """
SELECT entity_text, code_system, code, description, confidence,
       similarity(entity_text, :term) AS sim
FROM ontology_index
WHERE entity_text % :term
  AND code_system IN ({systems})
  {scope_clause}
ORDER BY sim DESC, confidence DESC NULLS LAST
LIMIT :top_k
"""


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("rds-data", region_name=region)


def ontology_lookup(
    term: str,
    code_systems: list[str] | None = None,
    top_k: int = 5,
    *,
    patient_scope: str | None = None,
    client: Any = None,
    resource_arn: str | None = None,
    secret_arn: str | None = None,
    database: str | None = None,
    region: str | None = None,
) -> list[OntologyMatch]:
    systems = [s.upper() for s in (code_systems or CODE_SYSTEMS)]
    bad = set(systems) - set(CODE_SYSTEMS)
    if bad:
        raise ValueError(f"unknown code system(s): {sorted(bad)}")

    resource_arn = resource_arn or os.environ.get("AURORA_CLUSTER_ARN")
    secret_arn = secret_arn or os.environ.get("AURORA_SECRET_ARN")
    database = database or os.environ.get("AURORA_DATABASE_NAME", "clinical_rag")
    if not resource_arn or not secret_arn:
        raise ValueError("AURORA_CLUSTER_ARN / AURORA_SECRET_ARN required")
    client = client or _client(region)

    # code systems are validated against a fixed allow-list above, so inlining
    # them as quoted literals is safe; `term` / `top_k` / scope stay bound.
    systems_sql = ", ".join(f"'{s}'" for s in systems)
    params = [
        {"name": "term", "value": {"stringValue": term}},
        {"name": "top_k", "value": {"longValue": int(top_k)}},
    ]
    scope_clause = ""
    if patient_scope:
        scope_clause = "AND patient_scope = :scope"
        params.append({"name": "scope", "value": {"stringValue": patient_scope}})

    sql = _SQL.format(systems=systems_sql, scope_clause=scope_clause)
    resp = client.execute_statement(
        resourceArn=resource_arn,
        secretArn=secret_arn,
        database=database,
        sql=sql,
        parameters=params,
    )
    return [_row_to_match(r) for r in resp.get("records", [])]


def _cell(cell: dict) -> Any:
    if cell.get("isNull"):
        return None
    for key in ("stringValue", "doubleValue", "longValue", "booleanValue"):
        if key in cell:
            return cell[key]
    return None


def _row_to_match(row: list[dict]) -> OntologyMatch:
    entity_text, code_system, code, description, confidence, sim = (_cell(c) for c in row)
    return OntologyMatch(
        entity_text=entity_text or "",
        code_system=code_system or "",
        code=str(code or ""),
        description=description,
        confidence=confidence,
        similarity=sim,
    )
