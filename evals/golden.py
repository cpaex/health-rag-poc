"""Load and slice the golden question set (SPEC.md §8).

One JSONL line per case:
  id, category, question, patient_scope, expected_citations[],
  expected_answer_contains[], [must_not_contain[]], [expect_refusal], [expect_no_answer]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

GOLDEN_PATH = Path(__file__).with_name("golden_questions.jsonl")

REQUIRED_CATEGORIES = {"dense", "ontology", "multi_step", "guardrail_refusal"}


@dataclass
class GoldenCase:
    id: str
    category: str
    question: str
    patient_scope: str
    expected_citations: list[str] = field(default_factory=list)
    expected_answer_contains: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    expect_refusal: bool = False
    expect_no_answer: bool = False

    @property
    def is_refusal(self) -> bool:
        return self.expect_refusal

    @property
    def scorable(self) -> bool:
        """RAGAS faithfulness/precision/recall only make sense for cases that
        should produce a grounded answer."""
        return not self.expect_refusal and not self.expect_no_answer


def load_golden(path: Path | str = GOLDEN_PATH) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        raw = json.loads(line)
        cases.append(
            GoldenCase(
                id=raw["id"],
                category=raw["category"],
                question=raw["question"],
                patient_scope=raw["patient_scope"],
                expected_citations=raw.get("expected_citations", []),
                expected_answer_contains=raw.get("expected_answer_contains", []),
                must_not_contain=raw.get("must_not_contain", []),
                expect_refusal=raw.get("expect_refusal", False),
                expect_no_answer=raw.get("expect_no_answer", False),
            )
        )
    return cases


def select_ci_subset(cases: list[GoldenCase], size: int) -> list[GoldenCase]:
    """Deterministic subset that always covers every REQUIRED_CATEGORY, then fills
    to ``size`` in id order. Stable across runs."""
    by_id = sorted(cases, key=lambda c: c.id)
    picked: list[GoldenCase] = []
    seen_ids: set[str] = set()

    for category in sorted(REQUIRED_CATEGORIES):
        for case in by_id:
            if case.category == category:
                picked.append(case)
                seen_ids.add(case.id)
                break

    for case in by_id:
        if len(picked) >= size:
            break
        if case.id not in seen_ids:
            picked.append(case)
            seen_ids.add(case.id)

    return sorted(picked[:size] if size >= len(REQUIRED_CATEGORIES) else picked, key=lambda c: c.id)
