"""Phase 6: AgentCore runtime entrypoint routes payloads into supervisor.answer."""

from __future__ import annotations

from agent import runtime_entrypoint


def test_handle_forwards_prompt_scope_and_token(monkeypatch) -> None:
    seen = {}

    def fake_answer(query, patient_scope, *, mode=None, token=None):
        seen.update(query=query, patient_scope=patient_scope, mode=mode, token=token)
        return {"answer": "ok", "patient_scope": patient_scope, "blocked": False}

    monkeypatch.setattr(runtime_entrypoint, "answer", fake_answer)

    out = runtime_entrypoint.handle(
        {"prompt": "does she react to contrast?", "patient_scope": "patient-001", "token": "tok"}
    )
    assert out["answer"] == "ok"
    assert seen == {
        "query": "does she react to contrast?",
        "patient_scope": "patient-001",
        "mode": "agentcore",
        "token": "tok",
    }


def test_handle_validates_required_fields(monkeypatch) -> None:
    monkeypatch.setattr(runtime_entrypoint, "answer", lambda *a, **k: {"answer": "x"})
    assert "error" in runtime_entrypoint.handle({"patient_scope": "patient-001"})
    assert "error" in runtime_entrypoint.handle({"prompt": "hi"})


def test_handler_alias_and_import_is_safe() -> None:
    assert runtime_entrypoint.handler is runtime_entrypoint.handle
    # module imports whether or not bedrock-agentcore is installed
    assert hasattr(runtime_entrypoint, "app")
