#!/usr/bin/env bash
# Run the full ingestion pipeline end-to-end against seed data (SPEC.md §6 step 6).
# Fleshed out in Phase 3.
set -euo pipefail

echo "[seed] TODO Phase 3:"
echo "  1. deidentify.py   (Comprehend Medical DetectPHI)"
echo "  2. ontology_link.py + ontology_index_load.py  (Infer* -> ontology_index)"
echo "  3. chunk.py"
echo "  4. embed_and_load.py  (Titan v2 -> bedrock_integration.bedrock_kb)"
echo "  5. trigger KB sync + smoke-test Retrieve API"
exit 0
