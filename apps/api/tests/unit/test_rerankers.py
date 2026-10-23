import pytest

from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.retrieval.packing import pack_context
from ragkit_server.retrieval.rerankers import RerankerPool, lexical_scores
from tests.unit.helpers import hit


def test_bm25_prefers_the_passage_that_answers() -> None:
    scores = lexical_scores(
        "how long do refunds take to arrive",
        [
            "Payouts are sent daily to your bank account.",
            "Refunds take five to ten business days to arrive on the customer's statement.",
            "Refunds can be partial.",
        ],
        ["Payouts", "Refunds", "Refunds"],
    )
    assert scores.index(max(scores)) == 1
    assert max(scores) == pytest.approx(1.0)


def test_identifiers_from_the_query_are_matched_exactly() -> None:
    scores = lexical_scores(
        "what does ACME-4011 mean",
        ["Error ACME-4012 means the card expired.", "Error ACME-4011 means insufficient funds."],
        ["", ""],
    )
    assert scores[1] > scores[0]


def test_headings_break_ties() -> None:
    scores = lexical_scores(
        "webhook retries",
        ["Events are sent again.", "Events are sent again."],
        ["Webhook retries", "Overview"],
    )
    assert scores[0] > scores[1]


async def test_lexical_rerank_sets_scores_and_ranks() -> None:
    pool = RerankerPool("unused-model", None)
    hits = [
        hit("Payouts are daily.", fused=0.9),
        hit("Refunds take five days to arrive.", fused=0.1),
    ]
    ordered, fallback = await pool.rerank("lexical", "how long do refunds take", hits)
    assert not fallback
    assert ordered[0].text.startswith("Refunds")
    assert [h.rerank_rank for h in ordered] == [1, 2]
    assert ordered[0].score == ordered[0].rerank_score


async def test_cross_encoder_failure_falls_back_to_lexical_once() -> None:
    pool = RerankerPool("unused-model", None)
    attempts = []

    async def broken(query, hits):  # type: ignore[no-untyped-def]
        attempts.append(query)
        raise RuntimeError("model files missing")

    pool.cross_encoder.score = broken  # type: ignore[method-assign]
    hits = [hit("Payouts are daily."), hit("Refunds take five days.")]
    _, first = await pool.rerank("cross-encoder", "refunds", hits)
    _, second = await pool.rerank("cross-encoder", "refunds", hits)
    assert first
    assert second
    assert len(attempts) == 1
    assert pool.cross_encoder_error is not None


async def test_no_reranking_keeps_the_order() -> None:
    pool = RerankerPool("unused-model", None)
    hits = [hit("b", fused=0.1), hit("a", fused=0.9)]
    ordered, fallback = await pool.rerank("none", "a", hits)
    assert ordered == hits
    assert not fallback


def test_packing_fills_the_budget_and_numbers_sources() -> None:
    counter = TokenCounter()
    hits = [hit("word " * 300), hit("short one"), hit("word " * 300), hit("another short")]
    packed = pack_context(hits, counter, budget=400, max_sources=3)
    assert [h.n for h in packed] == [1, 2, 3]
    assert packed[1].text == "short one"


def test_packing_keeps_the_best_passage_even_when_it_is_too_long() -> None:
    packed = pack_context([hit("word " * 900)], TokenCounter(), budget=100, max_sources=3)
    assert len(packed) == 1


def test_packing_counts_the_sentence_window_not_the_sentence() -> None:
    counter = TokenCounter()
    window = "Short sentence. " + "More context here. " * 100
    filler = hit("word " * 100)
    windowed = pack_context(
        [hit("Short sentence.", context=window), filler], counter, budget=450, max_sources=5
    )
    plain = pack_context([hit("Short sentence."), filler], counter, budget=450, max_sources=5)
    assert len(windowed) == 1
    assert len(plain) == 2
