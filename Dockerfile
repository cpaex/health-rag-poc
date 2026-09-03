# AgentCore Runtime image for the clinical RAG supervisor (SPEC.md §5, Phase 6).
#
# MUST be built for linux/arm64 — Agent Runtime only accepts ARM64 images.
# The agentcore Terraform module builds it with:
#   docker buildx build --platform linux/arm64 --provenance=false -t <ecr>:latest --push .
#
# Local sanity build:
#   docker buildx build --platform linux/arm64 -t clinical-rag-runtime:local --load .

FROM --platform=linux/arm64 python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DOCKER_CONTAINER=1

WORKDIR /app

# Dependency layer.
COPY pyproject.toml README.md ./
COPY agent/ ./agent/
RUN pip install --upgrade pip \
 && pip install ".[runtime]"

# Non-root, matching the AgentCore convention.
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

# AgentCore Runtime speaks HTTP on 8080.
EXPOSE 8080

CMD ["opentelemetry-instrument", "python", "-m", "agent.runtime_entrypoint"]
