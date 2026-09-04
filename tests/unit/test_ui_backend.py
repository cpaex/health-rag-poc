"""Phase 8: UI backend — mode resolution, citation rendering, dual-mode dispatch."""

from __future__ import annotations

import json

import pytest

from ui import backend


# ------------------------------- helpers ---------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        ("local", "local"),
        ("agentcore", "agentcore"),
        ("AGENTCORE", "agentcore"),
        ("", "local"),
        ("nonsense", "local"),
        (None, "local"),
    ],
)
def test_resolve_mode(value, expected) -> None:
    env = {} if value is None else {"AGENT_MODE": value}
    assert backend.resolve_mode(env) == expected


def test_extract_citations_orders_dedups_and_merges_extra() -> None:
    text = "See Note-001 and note-003; also NOTE-001 again."
    assert backend.extract_citations(text, extra=["note-010"]) == [
        "note-010",
        "note-001",
        "note-003",
    ]
    assert backend.extract_citations("") == []


def test_render_citations_markdown() -> None:
    assert "No source notes" in backend.render_citations_markdown([])
    md = backend.render_citations_markdown(["note-001", "note-003"])
    assert "`note-001`" in md and "`note-003`" in md


# ------------------------------- local mode ------------------------------- #
def test_run_query_local_extracts_citations_from_answer() -> None:
    def fake_local(q, scope, *, mode, token=None):
        assert mode == "local"
        return {
            "answer": "Per note-001 and note-010, premedicate.",
            "patient_scope": scope,
            "blocked": False,
        }

    view = backend.run_query("q", "patient-001", mode="local", local_fn=fake_local)
    assert view.mode == "local"
    assert view.citations == ["note-001", "note-010"]
    assert not view.blocked


def test_run_query_local_passes_blocked_through() -> None:
    def fake_local(q, scope, *, mode, token=None):
        return {
            "answer": "withheld",
            "blocked": True,
            "blocked_stage": "output",
            "patient_scope": scope,
        }

    view = backend.run_query("q", "patient-001", mode="local", local_fn=fake_local)
    assert view.blocked and view.blocked_stage == "output"


def test_run_query_local_maps_permission_error_to_identity_block() -> None:
    def fake_local(q, scope, *, mode, token=None):
        raise PermissionError("patient_scope 'patient-002' not authorized")

    view = backend.run_query("show patient-002", "patient-001", mode="local", local_fn=fake_local)
    assert view.blocked and view.blocked_stage == "identity"
    assert "not authorized" in view.error


# ---------------------------- agentcore mode ----------------------------- #
class FakeStream:
    def __init__(self, payload: bytes):
        self._p = payload

    def read(self) -> bytes:
        return self._p


class FakeAgentCore:
    def __init__(self, payload: dict):
        self.payload = payload
        self.last = None

    def invoke_agent_runtime(self, **kwargs):
        self.last = kwargs
        return {"response": FakeStream(json.dumps(self.payload).encode())}


def test_run_query_agentcore_builds_request_and_parses_response() -> None:
    fake = FakeAgentCore(
        {"answer": "See note-003.", "patient_scope": "patient-001", "blocked": False}
    )
    view = backend.run_query(
        "did she react?",
        "patient-001",
        mode="agentcore",
        token="tok",
        agentcore_client=fake,
        runtime_arn="arn:aws:bedrock-agentcore:us-east-1:1:runtime/x",
    )
    assert fake.last["agentRuntimeArn"].endswith("runtime/x")
    sent = json.loads(fake.last["payload"])
    assert sent == {"prompt": "did she react?", "patient_scope": "patient-001", "token": "tok"}
    assert view.mode == "agentcore"
    assert view.citations == ["note-003"]


def test_run_query_agentcore_requires_runtime_arn(monkeypatch) -> None:
    monkeypatch.delenv("AGENTCORE_RUNTIME_ARN", raising=False)
    view = backend.run_query("q", "patient-001", mode="agentcore", agentcore_client=object())
    assert view.error and "AGENTCORE_RUNTIME_ARN" in view.error


def test_run_query_validates_inputs() -> None:
    assert backend.run_query("", "patient-001", mode="local", local_fn=lambda *a, **k: {}).error
    assert backend.run_query("q", "  ", mode="local", local_fn=lambda *a, **k: {}).error
