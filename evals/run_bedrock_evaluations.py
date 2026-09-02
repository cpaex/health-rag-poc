"""Launch a real Bedrock Evaluations job (SPEC.md §8).

Retrieve-only: context relevance/coverage.
Retrieve-and-generate: correctness, completeness, faithfulness, citation precision/coverage.
Manually triggered (costs money, takes longer) — NOT a CI gate. Prints the job ID.
Implemented in Phase 7.
"""

from __future__ import annotations

import sys


def main() -> int:
    raise NotImplementedError("Phase 7: bedrock create_evaluation_job")


if __name__ == "__main__":
    sys.exit(main())
