"""Fast RAGAS gate for CI (SPEC.md §8).

Runs RAGAS ``faithfulness`` / ``context_precision`` / ``context_recall`` over a
small, category-covering subset of the golden set and fails the build if
faithfulness drops below ``FAITHFULNESS_THRESHOLD``. Guardrail-refusal and
no-context cases are checked separately (they have no grounded answer to score).

The model/RAGAS calls are injected (``runner``, ``ragas_fn``) so every branch is
unit-testable without AWS; ``main()`` with no injection wires the real supervisor.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.golden import (  # noqa: E402
    REQUIRED_CATEGORIES,
    GoldenCase,
    load_golden,
    select_ci_subset,
)

FAITHFULNESS_THRESHOLD = 0.80
SOFT_THRESHOLDS = {"context_precision": 0.55, "context_recall": 0.55}
CI_SUBSET_SIZE = 6


@dataclass
class RunResult:
    answer: str
    contexts: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    blocked: bool = False


def build_ragas_records(cases: list[GoldenCase], results: list[RunResult]) -> list[dict]:
    """Shape (question, answer, contexts, reference) records for RAGAS."""
    records = []
    for case, res in zip(cases, results, strict=True):
        records.append(
            {
                "question": case.question,
                "answer": res.answer,
                "contexts": list(res.contexts),
                # approximate ground truth from the expected substrings
                "reference": " ".join(case.expected_answer_contains) or case.question,
            }
        )
    return records


def gate(scores: dict[str, float]) -> tuple[bool, dict]:
    """True iff faithfulness meets its hard threshold. Soft metrics are reported
    but do not fail the build."""
    report = {
        "thresholds": {"faithfulness": FAITHFULNESS_THRESHOLD, **SOFT_THRESHOLDS},
        "scores": scores,
    }
    faith = scores.get("faithfulness")
    passed = faith is not None and faith >= FAITHFULNESS_THRESHOLD
    report["passed"] = passed
    report["soft_warnings"] = [m for m, thr in SOFT_THRESHOLDS.items() if scores.get(m, 1.0) < thr]
    return passed, report


def check_non_scorable(cases: list[GoldenCase], results: list[RunResult]) -> list[str]:
    """Refusal cases must be blocked; no-context cases must decline to answer."""
    failures: list[str] = []
    for case, res in zip(cases, results, strict=True):
        if case.expect_refusal and not res.blocked:
            failures.append(f"{case.id}: expected a guardrail/scope refusal, got an answer")
        if case.expect_no_answer:
            text = res.answer.lower()
            if not any(k in text for k in ("no ", "not ", "no information", "nothing", "retriev")):
                failures.append(f"{case.id}: expected 'no relevant info', got a substantive answer")
    return failures


def _default_runner(case: GoldenCase) -> RunResult:  # pragma: no cover - needs AWS
    from agent.retrieval_strategy import hybrid_multistep
    from agent.supervisor import SupervisorConfig, _ToolBundle, answer, bound_callables

    cfg = SupervisorConfig.from_env()
    strategy = hybrid_multistep(
        case.question, case.patient_scope, tools=_ToolBundle(bound_callables(cfg))
    )
    result = answer(case.question, case.patient_scope, mode="local")
    return RunResult(
        answer=result.get("answer", ""),
        contexts=[c.text for c in strategy.chunks],
        citations=[c.source_note_id for c in strategy.chunks],
        blocked=bool(result.get("blocked")),
    )


def _default_ragas_fn(records: list[dict]) -> dict[str, float]:  # pragma: no cover - needs AWS/LLM
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import context_precision, context_recall, faithfulness

    ds = Dataset.from_list(records)
    scores = evaluate(ds, metrics=[faithfulness, context_precision, context_recall])
    return {k: float(v) for k, v in scores.items()}


def run(
    *,
    golden_path: str | Path | None = None,
    subset_size: int = CI_SUBSET_SIZE,
    runner=_default_runner,
    ragas_fn=_default_ragas_fn,
) -> tuple[int, dict]:
    cases = load_golden(golden_path) if golden_path else load_golden()
    subset = select_ci_subset(cases, subset_size)
    results = [runner(c) for c in subset]

    non_scorable_failures = check_non_scorable(subset, results)

    scorable = [(c, r) for c, r in zip(subset, results, strict=True) if c.scorable]
    report: dict = {
        "subset": [c.id for c in subset],
        "non_scorable_failures": non_scorable_failures,
    }
    if scorable:
        records = build_ragas_records([c for c, _ in scorable], [r for _, r in scorable])
        scores = ragas_fn(records)
        passed, gate_report = gate(scores)
        report["ragas"] = gate_report
    else:
        passed = True

    ok = passed and not non_scorable_failures
    report["passed"] = ok
    return (0 if ok else 1), report


def self_check(golden_path: str | Path | None = None) -> tuple[int, dict]:
    """No-AWS CI gate: the golden set parses, covers every required category with
    >= 10 cases, refusal cases are flagged, and the CI subset selector still
    covers every required category. Also exercises gate() on a synthetic score."""
    cases = load_golden(golden_path) if golden_path else load_golden()
    problems: list[str] = []

    if len(cases) < 10:
        problems.append(f"golden set has {len(cases)} cases, need >= 10")
    present = {c.category for c in cases}
    missing = REQUIRED_CATEGORIES - present
    if missing:
        problems.append(f"missing required categories: {sorted(missing)}")
    for c in cases:
        if c.category == "guardrail_refusal" and not c.expect_refusal:
            problems.append(f"{c.id}: guardrail_refusal case without expect_refusal")
        if c.category == "multi_step" and len(c.expected_citations) < 1:
            problems.append(f"{c.id}: multi_step case without expected_citations")

    subset = select_ci_subset(cases, CI_SUBSET_SIZE)
    if not REQUIRED_CATEGORIES <= {c.category for c in subset}:
        problems.append("CI subset does not cover every required category")

    # gate() sanity
    if gate({"faithfulness": FAITHFULNESS_THRESHOLD})[0] is not True:
        problems.append("gate() rejected a score at the threshold")
    if gate({"faithfulness": FAITHFULNESS_THRESHOLD - 0.01})[0] is not False:
        problems.append("gate() accepted a score below the threshold")

    report = {
        "cases": len(cases),
        "categories": sorted(present),
        "ci_subset": [c.id for c in subset],
        "faithfulness_threshold": FAITHFULNESS_THRESHOLD,
        "problems": problems,
    }
    return (0 if not problems else 1), report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--golden", default=None)
    ap.add_argument("--subset-size", type=int, default=CI_SUBSET_SIZE)
    ap.add_argument(
        "--self-check",
        action="store_true",
        help="validate the golden set + gate logic without any model call (CI default)",
    )
    args = ap.parse_args(argv)

    if args.self_check:
        code, report = self_check(args.golden)
    else:
        code, report = run(golden_path=args.golden, subset_size=args.subset_size)
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
