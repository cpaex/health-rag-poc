"""Mocked JWT / patient-scope check middleware (SPEC.md §2, §7).

Non-goal for v1: real clinician SSO / SMART-on-FHIR launch. For local dev this
validates a mocked JWT with a configurable `patient_scope` claim and rejects any
request whose requested scope is outside the token's authorized scope.

EXTENSION POINT: swap `verify_token` for real Cognito/Entra federation via
AgentCore Identity. Do not remove the scope-check call site in supervisor.py.

Implemented in Phase 5.
"""

from __future__ import annotations


def verify_token(token: str) -> dict:
    """Return decoded claims incl. `patient_scope`. Phase 5."""
    raise NotImplementedError("Phase 5: mocked JWT verification")


def assert_scope_allowed(requested_scope: str, claims: dict) -> None:
    """Raise if `requested_scope` is not covered by `claims['patient_scope']`. Phase 5."""
    raise NotImplementedError("Phase 5: scope enforcement")
