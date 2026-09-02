#!/usr/bin/env python3
"""Phase 2 / Phase 3 smoke test for the Bedrock Knowledge Base.

Calls the Retrieve API with HYBRID search against the Aurora-backed KB and prints
the hits. Phase 2 Definition of Done: this returns without error once the KB
exists (it may return zero results until Phase 3 loads data). Phase 3 Definition
of Done: it returns non-empty, correctly patient-scoped results.

Usage:
  kb_smoke_test.py --kb-id <KNOWLEDGE_BASE_ID> \
      [--query "contrast dye reaction"] [--patient-scope patient-001] \
      [--top-k 5] [--region us-east-1]

Reads KNOWLEDGE_BASE_ID / AWS_REGION from the environment if flags are omitted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.tools.kb_hybrid_retrieve import build_retrieval_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb-id", default=os.environ.get("KNOWLEDGE_BASE_ID"))
    ap.add_argument("--query", default="adverse reaction to contrast dye")
    ap.add_argument("--patient-scope", default=None)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    args = ap.parse_args()

    if not args.kb_id:
        print("error: --kb-id or KNOWLEDGE_BASE_ID required", file=sys.stderr)
        return 2

    client = boto3.client("bedrock-agent-runtime", region_name=args.region)
    resp = client.retrieve(
        knowledgeBaseId=args.kb_id,
        retrievalQuery={"text": args.query},
        retrievalConfiguration=build_retrieval_config(args.top_k, args.patient_scope),
    )

    results = resp.get("retrievalResults", [])
    print(f"query   : {args.query!r}")
    print(f"scope   : {args.patient_scope or '(none)'}")
    print(f"results : {len(results)}")
    for i, r in enumerate(results, 1):
        score = r.get("score")
        text = (r.get("content", {}).get("text") or "").replace("\n", " ")[:160]
        meta = r.get("metadata", {})
        scope = meta.get("patient_scope", meta.get("custom_metadata", {}))
        print(f"  [{i}] score={score} scope={scope}")
        print(f"      {text}")

    if args.patient_scope:
        bad = [
            r
            for r in results
            if r.get("metadata", {}).get("patient_scope") not in (None, args.patient_scope)
        ]
        if bad:
            print(
                f"FAIL: {len(bad)} result(s) outside patient_scope={args.patient_scope}",
                file=sys.stderr,
            )
            return 1

    print(json.dumps({"ok": True, "count": len(results)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
