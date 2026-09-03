"""Mocked JWT / patient-scope enforcement (SPEC.md §2, §7).

Non-goal for v1: real clinician SSO / SMART-on-FHIR launch. For local dev a
"token" is a JSON object (optionally base64url-encoded) carrying at least
``patient_scope`` (a string or list of strings) and ``exp`` (unix seconds).

EXTENSION POINT: replace ``verify_token`` with real Cognito/Entra federation via
AgentCore Identity (validate signature + issuer + audience, map the SMART
``launch/patient`` context to ``patient_scope``). Keep ``authorize`` and its call
sites — every tool/model call must run through it.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time

MOCK_ISSUER = "mock-smart-on-fhir"


class IdentityError(Exception):
    """Bad or expired token."""


class ScopeError(PermissionError):
    """Requested patient scope is outside the token's authorization."""


def _decode(token: str) -> dict:
    token = token.strip()
    if not token:
        raise IdentityError("empty token")
    # Accept raw JSON or base64url(JSON).
    for loader in (lambda t: t, _b64url_to_text):
        try:
            claims = json.loads(loader(token))
            if isinstance(claims, dict):
                return claims
        except (ValueError, binascii.Error):
            continue
    raise IdentityError("token is not JSON or base64url-JSON")


def _b64url_to_text(token: str) -> str:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + pad).decode("utf-8")


def verify_token(token: str, *, now: float | None = None) -> dict:
    """Return decoded claims. Raises ``IdentityError`` if malformed or expired."""
    claims = _decode(token)
    now = time.time() if now is None else now

    exp = claims.get("exp")
    if exp is not None and float(exp) < now:
        raise IdentityError("token expired")

    scope = claims.get("patient_scope")
    if not scope or (isinstance(scope, list) and not all(isinstance(s, str) for s in scope)):
        raise IdentityError("token missing a usable patient_scope claim")
    return claims


def authorized_scopes(claims: dict) -> list[str]:
    scope = claims["patient_scope"]
    return [scope] if isinstance(scope, str) else list(scope)


def authorize(requested_scope: str, token: str | dict, *, now: float | None = None) -> str:
    """Return the effective patient scope to use for a session.

    ``token`` may be a raw token string or already-verified claims. The returned
    scope is ALWAYS one the token authorizes — a caller/UI-supplied
    ``requested_scope`` can only *select among* authorized scopes, never widen
    them.
    """
    claims = token if isinstance(token, dict) else verify_token(token, now=now)
    allowed = authorized_scopes(claims)
    if requested_scope not in allowed:
        raise ScopeError(f"patient_scope {requested_scope!r} not in authorized scopes {allowed!r}")
    return requested_scope


def assert_scope_allowed(requested_scope: str, claims: dict) -> None:
    """Raise ``ScopeError`` if ``requested_scope`` is not covered by ``claims``."""
    if requested_scope not in authorized_scopes(claims):
        raise ScopeError(
            f"patient_scope {requested_scope!r} not authorized ({authorized_scopes(claims)!r})"
        )


# --------------------------------------------------------------------------- #
# Prompt-side scope-escalation detection                                       #
# --------------------------------------------------------------------------- #
_ESCALATION_PATTERNS = [
    re.compile(r"\bignore (?:all|any|the)?\s*(?:previous|prior|above)\b", re.I),
    re.compile(r"\bdisregard (?:the )?(?:system|previous|prior)\b", re.I),
    re.compile(r"\b(all|other|every)\s+patients?\b", re.I),
    re.compile(r"\bcross[- ]patient\b", re.I),
    re.compile(r"\b(?:as|act as|you are now)\s+(?:an?\s+)?admin\b", re.I),
    re.compile(r"\b(patient-\d+)\b", re.I),
    re.compile(r"\b(MRN-\d{7})\b"),
]


def scan_for_scope_escalation(text: str, authorized_scope: str) -> list[str]:
    """Return snippets in ``text`` that look like attempts to widen patient scope
    or override instructions. Any other ``patient-XXX`` / MRN than the authorized
    one counts."""
    hits: list[str] = []
    for pat in _ESCALATION_PATTERNS:
        for m in pat.finditer(text or ""):
            ref = m.group(1) if m.groups() else m.group(0)
            if (
                ref
                and ref.lower().startswith("patient-")
                and ref.lower() == authorized_scope.lower()
            ):
                continue  # a mention of the authorized patient is fine
            hits.append(m.group(0))
    return hits


def guard_request(query: str, requested_scope: str, token: str | dict, *, now: float | None = None):
    """Verify the token, pin the effective scope, and reject a query that tries
    to escalate. Returns ``(effective_scope, claims)``; raises before any tool or
    model call."""
    claims = token if isinstance(token, dict) else verify_token(token, now=now)
    effective = authorize(requested_scope, claims, now=now)
    escalations = scan_for_scope_escalation(query, effective)
    if escalations:
        raise ScopeError(f"query rejected — scope-escalation attempt: {escalations}")
    return effective, claims
