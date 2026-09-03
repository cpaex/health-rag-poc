"""Bedrock Guardrails wrapper (SPEC.md §7).

Wraps ``bedrock-runtime:ApplyGuardrail`` so the supervisor can filter BOTH the
input to and the output of its final model call. Injectable client for tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

Source = Literal["INPUT", "OUTPUT"]


@dataclass
class GuardrailResult:
    action: str  # "NONE" | "GUARDRAIL_INTERVENED"
    text: str  # anonymized / blocked-message text if intervened, else the input
    blocked: bool  # True when the policy blocked (vs merely anonymized)
    raw: dict

    @property
    def intervened(self) -> bool:
        return self.action == "GUARDRAIL_INTERVENED"


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


class Guardrail:
    """Applies one Bedrock Guardrail. A no-op when no guardrail id is configured
    (so local runs without Phase 5 infra still work)."""

    def __init__(
        self,
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        *,
        client: Any = None,
        region: str | None = None,
    ) -> None:
        self.guardrail_id = guardrail_id or os.environ.get("BEDROCK_GUARDRAIL_ID")
        self.guardrail_version = (
            guardrail_version or os.environ.get("BEDROCK_GUARDRAIL_VERSION") or "DRAFT"
        )
        self._client = client
        self._region = region

    @property
    def enabled(self) -> bool:
        return bool(self.guardrail_id)

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = _client(self._region)
        return self._client

    def apply(self, text: str, source: Source) -> GuardrailResult:
        if not self.enabled:
            return GuardrailResult("NONE", text, False, {})
        resp = self._ensure_client().apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.guardrail_version,
            source=source,
            content=[{"text": {"text": text}}],
        )
        action = resp.get("action", "NONE")
        outputs = resp.get("outputs") or []
        out_text = outputs[0]["text"] if outputs else text
        blocked = action == "GUARDRAIL_INTERVENED" and _has_blocking_assessment(resp)
        return GuardrailResult(action, out_text, blocked, resp)

    def check_input(self, text: str) -> GuardrailResult:
        return self.apply(text, "INPUT")

    def check_output(self, text: str) -> GuardrailResult:
        return self.apply(text, "OUTPUT")


_BLOCK_KEYS = (
    "topicPolicy",
    "contentPolicy",
    "wordPolicy",
    "sensitiveInformationPolicy",
    "contextualGroundingPolicy",
)


def _has_blocking_assessment(resp: dict) -> bool:
    """True if any assessment recorded a BLOCK/BLOCKED action (vs ANONYMIZED)."""
    for assessment in resp.get("assessments", []):
        for key in _BLOCK_KEYS:
            policy = assessment.get(key) or {}
            for items in policy.values():
                for item in items if isinstance(items, list) else []:
                    if str(item.get("action", "")).upper() in ("BLOCKED", "BLOCK"):
                        return True
    return False
