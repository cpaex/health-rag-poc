"""Non-Streamlit logic for the UI (SPEC.md §9) — kept import-light and testable.

Two execution modes:
  * ``local``     -> runs agent.supervisor.answer() in-process
  * ``agentcore`` -> InvokeAgentRuntime against the deployed runtime

Both return an :class:`AnswerView` so the Streamlit layer renders one shape.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

VALID_MODES = ("local", "agentcore")
_CITATION_RE = re.compile(r"\bnote-\d+\b", re.IGNORECASE)


@dataclass
class AnswerView:
    answer: str
    citations: list[str] = field(default_factory=list)
    patient_scope: str = ""
    mode: str = "local"
    blocked: bool = False
    blocked_stage: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


def resolve_mode(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    mode = (env.get("AGENT_MODE") or "local").strip().lower()
    return mode if mode in VALID_MODES else "local"


def extract_citations(text: str, extra: list[str] | None = None) -> list[str]:
    """Ordered, de-duplicated ``note-NNN`` ids found in ``text`` plus any
    explicitly-provided ids (e.g. from a structured tool result)."""
    found = list(extra or [])
    found += [m.group(0).lower() for m in _CITATION_RE.finditer(text or "")]
    seen: dict[str, None] = {}
    for c in found:
        seen.setdefault(c.lower(), None)
    return list(seen)


def render_citations_markdown(citations: list[str]) -> str:
    if not citations:
        return "_No source notes cited._"
    return "**Sources:** " + ", ".join(f"`{c}`" for c in citations)


# --------------------------------------------------------------------------- #
# Mode implementations                                                         #
# --------------------------------------------------------------------------- #
def _run_local(question: str, patient_scope: str, token: str | None, local_fn: Any) -> AnswerView:
    if local_fn is None:
        from agent.supervisor import answer as local_fn  # lazy: pulls strands
    result = local_fn(question, patient_scope, mode="local", token=token)
    text = result.get("answer", "")
    return AnswerView(
        answer=text,
        citations=extract_citations(text, result.get("citations")),
        patient_scope=result.get("patient_scope", patient_scope),
        mode="local",
        blocked=bool(result.get("blocked")),
        blocked_stage=result.get("blocked_stage"),
        raw=result,
    )


def _run_agentcore(
    question: str,
    patient_scope: str,
    token: str | None,
    client: Any,
    runtime_arn: str | None,
) -> AnswerView:
    runtime_arn = runtime_arn or os.environ.get("AGENTCORE_RUNTIME_ARN")
    if not runtime_arn:
        return AnswerView(answer="", mode="agentcore", error="AGENTCORE_RUNTIME_ARN not set")
    if client is None:
        import boto3

        client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION"))

    payload = {"prompt": question, "patient_scope": patient_scope}
    if token:
        payload["token"] = token
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn, payload=json.dumps(payload).encode("utf-8")
    )
    body = resp.get("response")
    text_body = body.read().decode("utf-8") if hasattr(body, "read") else str(body)
    try:
        data = json.loads(text_body)
    except (ValueError, TypeError):
        data = {"answer": text_body}

    text = data.get("answer", "") if isinstance(data, dict) else str(data)
    return AnswerView(
        answer=text,
        citations=extract_citations(
            text, data.get("citations") if isinstance(data, dict) else None
        ),
        patient_scope=(data.get("patient_scope") if isinstance(data, dict) else None)
        or patient_scope,
        mode="agentcore",
        blocked=bool(isinstance(data, dict) and data.get("blocked")),
        blocked_stage=data.get("blocked_stage") if isinstance(data, dict) else None,
        raw=data if isinstance(data, dict) else {"answer": text},
    )


def run_query(
    question: str,
    patient_scope: str,
    *,
    mode: str | None = None,
    token: str | None = None,
    local_fn: Any = None,
    agentcore_client: Any = None,
    runtime_arn: str | None = None,
) -> AnswerView:
    mode = (mode or resolve_mode()).lower()
    if not question.strip():
        return AnswerView(answer="", mode=mode, error="question is empty")
    if not patient_scope.strip():
        return AnswerView(answer="", mode=mode, error="patient_scope is required")

    try:
        if mode == "agentcore":
            return _run_agentcore(question, patient_scope, token, agentcore_client, runtime_arn)
        return _run_local(question, patient_scope, token, local_fn)
    except PermissionError as e:  # identity / scope rejection from the supervisor
        return AnswerView(
            answer="", mode=mode, blocked=True, blocked_stage="identity", error=str(e)
        )
