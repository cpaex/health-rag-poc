"""Phase 5: ApplyGuardrail wrapper — request shape, block vs anonymize, no-op."""

from __future__ import annotations

from agent.guardrails import Guardrail


class FakeGR:
    def __init__(self, resp: dict) -> None:
        self.resp = resp
        self.calls: list[dict] = []

    def apply_guardrail(self, **kwargs):
        self.calls.append(kwargs)
        return self.resp


NONE_RESP = {"action": "NONE", "outputs": []}
BLOCK_RESP = {
    "action": "GUARDRAIL_INTERVENED",
    "outputs": [{"text": "Blocked by policy."}],
    "assessments": [
        {"topicPolicy": {"topics": [{"name": "treatment_directive", "action": "BLOCKED"}]}}
    ],
}
ANON_RESP = {
    "action": "GUARDRAIL_INTERVENED",
    "outputs": [{"text": "Patient {NAME} on {PHONE}"}],
    "assessments": [
        {"sensitiveInformationPolicy": {"piiEntities": [{"type": "NAME", "action": "ANONYMIZED"}]}}
    ],
}


def test_request_shape_input_and_output() -> None:
    fake = FakeGR(NONE_RESP)
    gr = Guardrail("gr-123", "DRAFT", client=fake)
    gr.check_input("hello")
    gr.check_output("world")
    assert [c["source"] for c in fake.calls] == ["INPUT", "OUTPUT"]
    assert fake.calls[0]["guardrailIdentifier"] == "gr-123"
    assert fake.calls[0]["guardrailVersion"] == "DRAFT"
    assert fake.calls[0]["content"] == [{"text": {"text": "hello"}}]


def test_blocking_assessment_sets_blocked() -> None:
    gr = Guardrail("gr-1", client=FakeGR(BLOCK_RESP))
    res = gr.check_output("Start 40mg furosemide now")
    assert res.intervened and res.blocked
    assert res.text == "Blocked by policy."


def test_anonymize_intervenes_without_blocking() -> None:
    gr = Guardrail("gr-1", client=FakeGR(ANON_RESP))
    res = gr.check_input("Patient Maria on 617-555-0142")
    assert res.intervened and not res.blocked
    assert res.text == "Patient {NAME} on {PHONE}"


def test_no_guardrail_id_is_noop() -> None:
    fake = FakeGR(NONE_RESP)
    gr = Guardrail(None, client=fake)
    res = gr.check_input("anything")
    assert not gr.enabled
    assert res.action == "NONE" and res.text == "anything" and fake.calls == []
