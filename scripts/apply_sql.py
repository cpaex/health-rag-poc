#!/usr/bin/env python3
"""Apply a .sql file to an Aurora cluster over the RDS Data API.

Used by the data_aurora Terraform module's schema_bootstrap null_resource and by
scripts/seed_demo_data.sh. Splits the file into statements on top-level `;`,
skips SQL comments, and executes them in order. Statements are expected to be
idempotent (CREATE ... IF NOT EXISTS).

Usage:
  apply_sql.py --resource-arn <cluster-arn> --secret-arn <secret-arn> \
               --database <db> --file <path.sql> [--region us-east-1]
"""

from __future__ import annotations

import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError


def split_statements(sql: str) -> list[str]:
    """Naive splitter: strip line comments, split on ';'. Good enough for the
    migration DDL in this repo (no PL/pgSQL bodies, no ';' inside literals)."""
    lines: list[str] = []
    for raw in sql.splitlines():
        stripped = raw.strip()
        if stripped.startswith("--") or not stripped:
            continue
        lines.append(raw)
    body = "\n".join(lines)
    return [s.strip() for s in body.split(";") if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resource-arn", required=True)
    ap.add_argument("--secret-arn", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--region", default=None)
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as fh:
        statements = split_statements(fh.read())

    client = boto3.client("rds-data", region_name=args.region)

    # Serverless v2 with min_capacity 0 can be paused; retry a few times while it wakes.
    for attempt in range(1, 11):
        try:
            client.execute_statement(
                resourceArn=args.resource_arn,
                secretArn=args.secret_arn,
                database=args.database,
                sql="SELECT 1",
            )
            break
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("DatabaseResumingException", "StatementTimeoutException") and attempt < 10:
                print(f"[apply_sql] cluster waking ({code}), retry {attempt}/10...", file=sys.stderr)
                time.sleep(10)
                continue
            raise

    for i, stmt in enumerate(statements, 1):
        preview = " ".join(stmt.split())[:80]
        print(f"[apply_sql] ({i}/{len(statements)}) {preview}")
        client.execute_statement(
            resourceArn=args.resource_arn,
            secretArn=args.secret_arn,
            database=args.database,
            sql=stmt,
        )

    print(f"[apply_sql] applied {len(statements)} statement(s) to {args.database}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
