"""AgentCore Runtime entrypoint (SPEC.md §5/§12 Phase 6).

Packaged ARM64 (see ``Dockerfile``) and invoked via ``InvokeAgentRuntime`` /
``agentcore invoke``. Delegates to ``agent.supervisor.answer`` — which runs
identity/scope enforcement → Guardrails INPUT → the Strands supervisor + Bedrock
model → Guardrails OUTPUT.

Invocation payload:
    {"prompt": "<question>", "patient_scope": "patient-001", "token": "<mock jwt>"}

``bedrock-agentcore`` is only needed inside the container (``pip install
'.[runtime]'``); importing this module without it still works so CI/tests can
import ``handler``.
"""

from __future__ import annotations

import os
from typing import Any

from agent.supervisor import answer


def handle(payload: dict, context: Any = None) -> dict:
    """Framework-agnostic core: one invocation -> one answer dict."""
    query = payload.get("prompt") or payload.get("query") or ""
    patient_scope = (
        payload.get("patient_scope")
        or payload.get("patientScope")
        or os.environ.get("DEFAULT_PATIENT_SCOPE", "")
    )
    if not query:
        return {"error": "payload.prompt is required"}
    if not patient_scope:
        return {"error": "payload.patient_scope is required"}

    return answer(
        query,
        patient_scope,
        mode="agentcore",
        token=payload.get("token"),
    )


# Back-compat alias (older callers imported ``handler``).
handler = handle


def build_app() -> Any:
    """Wrap :func:`handle` in a ``BedrockAgentCoreApp``. Requires ``bedrock-agentcore``."""
    from bedrock_agentcore import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload: dict, context: Any = None) -> dict:  # noqa: ANN001
        return handle(payload, context)

    return app


try:  # available in the container image; optional elsewhere
    app = build_app()
except ImportError:  # pragma: no cover - depends on env
    app = None


if __name__ == "__main__":
    if app is None:
        raise SystemExit("bedrock-agentcore not installed; run: pip install -e '.[runtime]'")
    app.run()
