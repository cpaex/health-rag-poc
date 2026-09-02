"""Phase 4: rerank — Bedrock Rerank request shape + index-to-text mapping."""

from __future__ import annotations

from agent.tools.rerank import rerank


class FakeRerank:
    def __init__(self, results):
        self.results = results
        self.last = None

    def rerank(self, **kwargs):
        self.last = kwargs
        return {"results": self.results}


def test_request_shape_matches_bedrock_rerank_api() -> None:
    fake = FakeRerank([{"index": 1, "relevanceScore": 0.9}, {"index": 0, "relevanceScore": 0.4}])
    rerank("what reaction?", ["passage zero", "passage one"], 2, client=fake, model_arn="arn:m")
    req = fake.last
    assert req["queries"] == [{"type": "TEXT", "textQuery": {"text": "what reaction?"}}]
    assert req["sources"][0] == {
        "type": "INLINE",
        "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": "passage zero"}},
    }
    brc = req["rerankingConfiguration"]["bedrockRerankingConfiguration"]
    assert brc["modelConfiguration"]["modelArn"] == "arn:m"
    assert brc["numberOfResults"] == 2


def test_results_mapped_back_to_candidate_text_in_returned_order() -> None:
    fake = FakeRerank([{"index": 2, "relevanceScore": 0.95}, {"index": 0, "relevanceScore": 0.5}])
    out = rerank("q", ["a", "b", "c"], 2, client=fake, model_arn="arn:m")
    assert [(r.index, r.text, round(r.relevance_score, 2)) for r in out] == [
        (2, "c", 0.95),
        (0, "a", 0.5),
    ]


def test_empty_candidates_short_circuits() -> None:
    fake = FakeRerank([])
    assert rerank("q", [], 5, client=fake) == []
    assert fake.last is None


def test_number_of_results_capped_at_candidate_count() -> None:
    fake = FakeRerank([{"index": 0, "relevanceScore": 1.0}])
    rerank("q", ["only one"], 10, client=fake, model_arn="arn:m")
    brc = fake.last["rerankingConfiguration"]["bedrockRerankingConfiguration"]
    assert brc["numberOfResults"] == 1
