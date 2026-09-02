"""Phase 3: Titan embed request shape + RDS Data API insert + id capture."""

from __future__ import annotations

import json

from ingestion import embed_and_load


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._p = payload

    def read(self) -> bytes:
        return self._p


class FakeBedrock:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def invoke_model(self, modelId: str, body: str) -> dict:  # noqa: N803
        self.requests.append({"modelId": modelId, "body": json.loads(body)})
        return {"body": FakeBody(json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode())}


class FakeRdsData:
    def __init__(self) -> None:
        self.statements: list[dict] = []
        self._n = 0

    def execute_statement(self, **kwargs) -> dict:
        self.statements.append(kwargs)
        self._n += 1
        return {"records": [[{"stringValue": f"00000000-0000-0000-0000-00000000000{self._n}"}]]}


def test_embed_requests_titan_v2_with_dimensions_and_normalize() -> None:
    fake = FakeBedrock()
    out = embed_and_load.embed(["hello", "world"], client=fake)
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert fake.requests[0]["modelId"] == "amazon.titan-embed-text-v2:0"
    assert fake.requests[0]["body"] == {"inputText": "hello", "dimensions": 1024, "normalize": True}


def test_load_chunks_inserts_and_returns_ids_in_order() -> None:
    fake = FakeRdsData()
    rows = [
        {
            "text": "chunk a",
            "embedding": [0.0, 1.0],
            "metadata": {},
            "custom_metadata": {"patient_scope": "patient-001"},
        },
        {
            "text": "chunk b",
            "embedding": [1.0, 0.0],
            "metadata": {},
            "custom_metadata": {"patient_scope": "patient-001"},
        },
    ]
    ids = embed_and_load.load_chunks(
        rows, resource_arn="arn:c", secret_arn="arn:s", database="clinical_rag", client=fake
    )
    assert ids == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ]
    first = fake.statements[0]
    assert "CAST(:embedding AS vector)" in first["sql"]
    params = {p["name"]: p["value"] for p in first["parameters"]}
    assert params["embedding"]["stringValue"] == "[0.0,1.0]"
    assert json.loads(params["custom_metadata"]["stringValue"])["patient_scope"] == "patient-001"
