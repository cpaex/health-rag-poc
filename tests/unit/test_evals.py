"""Phase 7: golden set integrity + RAGAS-gate logic + Bedrock eval job spec.

No AWS / no LLM — runner and ragas function are injected.
"""

from __future__ import annotations

import json

from evals import run_bedrock_evaluations as rbe
from evals import run_ragas_ci as ci
from evals.golden import REQUIRED_CATEGORIES, load_golden, select_ci_subset


# ----------------------------- golden set ----------------------------------- #
def test_golden_set_covers_required_categories_and_size() -> None:
    cases = load_golden()
    assert len(cases) >= 10
    assert REQUIRED_CATEGORIES <= {c.category for c in cases}
    assert len({c.id for c in cases}) == len(cases)


def test_refusal_and_multistep_and_scope_cases_are_well_formed() -> None:
    cases = {c.id: c for c in load_golden()}
    refusals = [c for c in cases.values() if c.category == "guardrail_refusal"]
    assert refusals and all(c.expect_refusal for c in refusals)
    multi = [c for c in cases.values() if c.category == "multi_step"]
    assert any(len(c.expected_citations) >= 2 for c in multi)
    assert cases["g09"].must_not_contain  # scope isolation case
    assert cases["g10"].expect_no_answer


def test_select_ci_subset_is_deterministic_and_category_complete() -> None:
    cases = load_golden()
    a = select_ci_subset(cases, 6)
    b = select_ci_subset(cases, 6)
    assert [c.id for c in a] == [c.id for c in b]
    assert REQUIRED_CATEGORIES <= {c.category for c in a}
    assert len({c.id for c in a}) == len(a)


# ----------------------------- RAGAS gate ---------------------------------- #
def test_gate_passes_only_when_faithfulness_meets_threshold() -> None:
    ok, rep = ci.gate({"faithfulness": 0.9, "context_precision": 0.4})
    assert ok and rep["passed"]
    assert "context_precision" in rep["soft_warnings"]

    bad, rep2 = ci.gate({"faithfulness": 0.5})
    assert not bad and rep2["passed"] is False

    missing, _ = ci.gate({"context_recall": 0.9})
    assert not missing


def test_check_non_scorable_flags_bad_refusal_and_bad_no_answer() -> None:
    cases = load_golden()
    g11 = next(c for c in cases if c.id == "g11")  # refusal
    g10 = next(c for c in cases if c.id == "g10")  # no-answer

    fails = ci.check_non_scorable(
        [g11, g10],
        [
            ci.RunResult(answer="here are the meds ...", blocked=False),
            ci.RunResult(answer="The patient is on metformin."),
        ],
    )
    assert any("g11" in f for f in fails) and any("g10" in f for f in fails)

    passes = ci.check_non_scorable(
        [g11, g10],
        [
            ci.RunResult(answer="Request outside authorized scope.", blocked=True),
            ci.RunResult(answer="No relevant information was retrieved."),
        ],
    )
    assert passes == []


def test_run_end_to_end_with_fakes_pass_and_fail() -> None:
    good_runner = lambda c: ci.RunResult(  # noqa: E731
        answer=(
            "Request outside authorized scope."
            if c.expect_refusal
            else "No information retrieved."
            if c.expect_no_answer
            else "Grounded answer."
        ),
        contexts=["ctx"],
        blocked=c.expect_refusal,
    )
    code, report = ci.run(runner=good_runner, ragas_fn=lambda recs: {"faithfulness": 0.95})
    assert code == 0 and report["passed"]

    code2, _ = ci.run(runner=good_runner, ragas_fn=lambda recs: {"faithfulness": 0.4})
    assert code2 == 1

    leaky_runner = lambda c: ci.RunResult(answer="leaked meds", blocked=False)  # noqa: E731
    code3, rep3 = ci.run(runner=leaky_runner, ragas_fn=lambda recs: {"faithfulness": 0.99})
    assert code3 == 1 and rep3["non_scorable_failures"]


def test_self_check_passes_on_the_real_golden_set() -> None:
    code, report = ci.self_check()
    assert code == 0
    assert report["problems"] == []
    assert report["cases"] >= 10
    assert set(REQUIRED_CATEGORIES) <= set(report["categories"])


def test_self_check_fails_on_a_broken_golden_file(tmp_path) -> None:
    bad = tmp_path / "g.jsonl"
    bad.write_text(
        '{"id": "b1", "category": "dense", "question": "q", "patient_scope": "p", '
        '"expected_citations": [], "expected_answer_contains": []}\n'
    )
    code, report = ci.self_check(str(bad))
    assert code == 1
    assert any("required categories" in p for p in report["problems"])


def test_build_ragas_records_shape() -> None:
    cases = [c for c in load_golden() if c.scorable][:2]
    results = [ci.RunResult(answer="a", contexts=["x", "y"]) for _ in cases]
    recs = ci.build_ragas_records(cases, results)
    assert recs[0].keys() == {"question", "answer", "contexts", "reference"}
    assert recs[0]["contexts"] == ["x", "y"]
    assert recs[0]["reference"]  # non-empty pseudo ground truth


# ----------------------- Bedrock Evaluations spec ------------------------- #
def test_golden_to_jsonl_excludes_non_scorable_and_is_valid() -> None:
    text = rbe.golden_to_jsonl(load_golden())
    rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    scorable = [c for c in load_golden() if c.scorable]
    assert len(rows) == len(scorable)
    turn = rows[0]["conversationTurns"][0]
    assert turn["prompt"]["content"][0]["text"]
    assert turn["referenceResponses"][0]["content"][0]["text"]


def test_build_evaluation_job_spec_has_rag_retrieve_and_generate() -> None:
    spec = rbe.build_evaluation_job_spec(
        job_name="j1",
        role_arn="arn:aws:iam::1:role/eval",
        knowledge_base_id="KB123",
        generation_model_arn="arn:aws:bedrock:us-east-1::foundation-model/model",
        evaluator_model_id="anthropic.claude-x",
        dataset_s3_uri="s3://b/golden.jsonl",
        output_s3_uri="s3://b/out/",
    )
    assert spec["applicationType"] == "RagEvaluation"
    rag = spec["inferenceConfig"]["ragConfigs"][0]["knowledgeBaseConfig"]
    assert rag["retrieveConfig"]["knowledgeBaseId"] == "KB123"
    assert rag["retrieveAndGenerateConfig"]["type"] == "KNOWLEDGE_BASE"
    assert (
        rag["retrieveConfig"]["knowledgeBaseRetrievalConfiguration"]["vectorSearchConfiguration"][
            "overrideSearchType"
        ]
        == "HYBRID"
    )
    metrics = spec["evaluationConfig"]["automated"]["datasetMetricConfigs"][0]["metricNames"]
    assert "Builtin.Faithfulness" in metrics and "Builtin.ContextRelevance" in metrics


def test_launch_calls_create_evaluation_job_and_returns_id() -> None:
    class FakeBedrock:
        def __init__(self):
            self.spec = None

        def create_evaluation_job(self, **kwargs):
            self.spec = kwargs
            return {
                "jobArn": "arn:aws:bedrock:us-east-1:1:evaluation-job/abc",
                "status": "InProgress",
            }

    fake = FakeBedrock()
    out = rbe.launch({"jobName": "j1", "roleArn": "r"}, client=fake)
    assert out["jobArn"].endswith("/abc")
    assert fake.spec["jobName"] == "j1"
