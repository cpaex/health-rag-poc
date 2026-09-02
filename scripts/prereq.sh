#!/usr/bin/env bash
# Prerequisite checks for the dev environment (SPEC.md §3). Fleshed out in Phase 1.
set -euo pipefail

echo "[prereq] checking toolchain..."
command -v terraform >/dev/null || { echo "missing: terraform"; exit 1; }
command -v aws       >/dev/null || { echo "missing: aws cli"; exit 1; }
command -v python3   >/dev/null || { echo "missing: python3"; exit 1; }

echo "[prereq] TODO Phase 1: verify AWS creds, region, Bedrock model access,"
echo "         AgentCore starter toolkit (agentcore CLI), tflint."
echo "[prereq] ok (scaffold)"
