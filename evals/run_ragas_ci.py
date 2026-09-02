"""Fast RAGAS check for CI (SPEC.md §8).

Runs RAGAS `faithfulness`, `context_precision`, `context_recall` against a small
fixed subset of golden_questions.jsonl on every PR. Exits non-zero if faithfulness
drops below FAITHFULNESS_THRESHOLD. Implemented in Phase 7.
"""

from __future__ import annotations

import sys

FAITHFULNESS_THRESHOLD = 0.80  # tune in Phase 7
CI_SUBSET_SIZE = 4


def main() -> int:
    raise NotImplementedError("Phase 7: RAGAS eval over golden subset")


if __name__ == "__main__":
    sys.exit(main())
