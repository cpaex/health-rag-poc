"""Launch a managed Amazon Bedrock Evaluations job over the Knowledge Base (SPEC §8).

Manually triggered (costs money, minutes-to-hours) — NOT a CI gate. Builds the
dataset from the golden set, uploads it to S3, calls ``bedrock:CreateEvaluationJob``
for a RAG evaluation (retrieve-only + retrieve-and-generate), and prints the job id.

Request shape verified against botocore ``bedrock.CreateEvaluationJob`` (2026-09).
Metric identifiers are Bedrock built-ins — reconcile against the Bedrock console /
``knowledge-base-eval-retrieve-generate.html`` before a real run; wrong names are
rejected at ``CreateEvaluationJob`` time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.golden import GoldenCase, load_golden  # noqa: E402

RETRIEVE_METRICS = ["Builtin.ContextRelevance", "Builtin.ContextCoverage"]
RETRIEVE_AND_GENERATE_METRICS = [
    "Builtin.Correctness",
    "Builtin.Completeness",
    "Builtin.Faithfulness",
    "Builtin.CitationPrecision",
    "Builtin.CitationCoverage",
]


def golden_to_jsonl(cases: list[GoldenCase]) -> str:
    """Bedrock Evaluations dataset format: one JSON object per line with a
    ``prompt`` and optional ``referenceResponses``."""
    lines = []
    for c in cases:
        if not c.scorable:
            continue  # refusal / no-context cases aren't part of a RAG quality eval
        lines.append(
            json.dumps(
                {
                    "conversationTurns": [
                        {
                            "prompt": {"content": [{"text": c.question}]},
                            "referenceResponses": [
                                {"content": [{"text": " ".join(c.expected_answer_contains)}]}
                            ],
                        }
                    ]
                }
            )
        )
    return "\n".join(lines) + "\n"


def build_evaluation_job_spec(
    *,
    job_name: str,
    role_arn: str,
    knowledge_base_id: str,
    generation_model_arn: str,
    evaluator_model_id: str,
    dataset_s3_uri: str,
    output_s3_uri: str,
) -> dict:
    """Assemble the CreateEvaluationJob request for a KB RAG evaluation."""
    dataset = {"name": "golden", "datasetLocation": {"s3Uri": dataset_s3_uri}}
    return {
        "jobName": job_name,
        "jobDescription": "Clinical RAG golden-set evaluation (retrieve + retrieve-and-generate)",
        "roleArn": role_arn,
        "applicationType": "RagEvaluation",
        "evaluationConfig": {
            "automated": {
                "datasetMetricConfigs": [
                    {
                        "taskType": "General",
                        "dataset": dataset,
                        "metricNames": RETRIEVE_METRICS + RETRIEVE_AND_GENERATE_METRICS,
                    }
                ],
                "evaluatorModelConfig": {
                    "bedrockEvaluatorModels": [{"modelIdentifier": evaluator_model_id}]
                },
            }
        },
        "inferenceConfig": {
            "ragConfigs": [
                {
                    "knowledgeBaseConfig": {
                        "retrieveConfig": {
                            "knowledgeBaseId": knowledge_base_id,
                            "knowledgeBaseRetrievalConfiguration": {
                                "vectorSearchConfiguration": {
                                    "numberOfResults": 10,
                                    "overrideSearchType": "HYBRID",
                                }
                            },
                        },
                        "retrieveAndGenerateConfig": {
                            "type": "KNOWLEDGE_BASE",
                            "knowledgeBaseConfiguration": {
                                "knowledgeBaseId": knowledge_base_id,
                                "modelArn": generation_model_arn,
                                "retrievalConfiguration": {
                                    "vectorSearchConfiguration": {
                                        "numberOfResults": 10,
                                        "overrideSearchType": "HYBRID",
                                    }
                                },
                            },
                        },
                    }
                }
            ]
        },
        "outputDataConfig": {"s3Uri": output_s3_uri},
    }


def launch(spec: dict, *, client=None, region: str | None = None) -> dict:
    if client is None:  # pragma: no cover - needs AWS
        import boto3

        client = boto3.client("bedrock", region_name=region)
    resp = client.create_evaluation_job(**spec)
    return {"jobArn": resp.get("jobArn"), "jobName": spec["jobName"], "status": resp.get("status")}


def _upload_dataset(jsonl: str, s3_uri: str, *, client=None) -> str:  # pragma: no cover - needs AWS
    import boto3

    client = client or boto3.client("s3")
    assert s3_uri.startswith("s3://")
    bucket, _, key = s3_uri[len("s3://") :].partition("/")
    client.put_object(Bucket=bucket, Key=key, Body=jsonl.encode("utf-8"))
    return s3_uri


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-name", required=True)
    ap.add_argument("--role-arn", required=True)
    ap.add_argument("--knowledge-base-id", required=True)
    ap.add_argument("--generation-model-arn", required=True)
    ap.add_argument("--evaluator-model-id", default="anthropic.claude-3-5-sonnet-20241022-v2:0")
    ap.add_argument("--dataset-s3-uri", required=True, help="s3://.../golden.jsonl (written here)")
    ap.add_argument("--output-s3-uri", required=True)
    ap.add_argument("--region", default=None)
    args = ap.parse_args(argv)

    jsonl = golden_to_jsonl(load_golden())
    _upload_dataset(jsonl, args.dataset_s3_uri)

    spec = build_evaluation_job_spec(
        job_name=args.job_name,
        role_arn=args.role_arn,
        knowledge_base_id=args.knowledge_base_id,
        generation_model_arn=args.generation_model_arn,
        evaluator_model_id=args.evaluator_model_id,
        dataset_s3_uri=args.dataset_s3_uri,
        output_s3_uri=args.output_s3_uri,
    )
    result = launch(spec, region=args.region)
    print(json.dumps(result, indent=2))
    return 0 if result.get("jobArn") else 1


if __name__ == "__main__":
    sys.exit(main())
