"""Phase 3: DetectPHI wrapper — offsets rebased, spans redacted right-to-left."""

from __future__ import annotations

from ingestion import deidentify


class FakeCM:
    """Stand-in for boto3 comprehendmedical (not covered by moto)."""

    def __init__(self, entities_by_call: list[list[dict]]) -> None:
        self._calls = list(entities_by_call)
        self.seen: list[str] = []

    def detect_phi(self, Text: str) -> dict:  # noqa: N803
        self.seen.append(Text)
        return {"Entities": self._calls.pop(0)}


def test_detect_phi_single_request() -> None:
    text = "Patient Maria Tavares, MRN-0010001, called today."
    fake = FakeCM(
        [
            [
                {
                    "Type": "NAME",
                    "Text": "Maria Tavares",
                    "BeginOffset": 8,
                    "EndOffset": 21,
                    "Score": 0.99,
                },
                {
                    "Type": "ID",
                    "Text": "MRN-0010001",
                    "BeginOffset": 23,
                    "EndOffset": 34,
                    "Score": 0.98,
                },
            ]
        ]
    )
    ents = deidentify.detect_phi(text, client=fake)
    assert [e["Type"] for e in ents] == ["NAME", "ID"]
    assert fake.seen == [text]


def test_redact_replaces_spans_with_typed_placeholders() -> None:
    text = "Patient Maria Tavares, MRN-0010001, called today."
    ents = [
        {"Type": "NAME", "Text": "Maria Tavares", "BeginOffset": 8, "EndOffset": 21},
        {"Type": "ID", "Text": "MRN-0010001", "BeginOffset": 23, "EndOffset": 34},
    ]
    assert deidentify.redact(text, ents) == "Patient [NAME], [ID], called today."


def test_long_text_is_chunked_and_offsets_rebased() -> None:
    # Force two requests by shrinking the limit.
    deidentify._MAX_BYTES, original = 20, deidentify._MAX_BYTES
    try:
        text = "aaaaaaaaaa" + "bob smith " + "cccccccccc"  # 30 chars, name at 10..19
        fake = FakeCM(
            [
                [],  # first 20-byte piece: "aaaaaaaaaabob smith " -> pretend nothing
                [{"Type": "NAME", "Text": "cccc", "BeginOffset": 0, "EndOffset": 4, "Score": 0.9}],
            ]
        )
        ents = deidentify.detect_phi(text, client=fake)
        assert len(fake.seen) == 2
        # second piece starts at char 20, so offset 0 -> 20
        assert ents[0]["BeginOffset"] == 20 and ents[0]["EndOffset"] == 24
    finally:
        deidentify._MAX_BYTES = original
