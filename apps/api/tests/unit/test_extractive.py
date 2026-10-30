import numpy as np

from ragkit_server.ai.citations import best_quote, extract_citations
from ragkit_server.ai.extractive import NOT_FOUND, answer_units, extractive_answer
from tests.unit.helpers import hit


def test_answers_with_the_best_sentence_and_cites_it() -> None:
    sources = [
        hit(
            "Refunds\n\nRefunds can be issued up to 180 days after the original charge. "
            "Fees are not returned.",
            n=1,
            title="Refunds and disputes",
        ),
        hit("Payouts\n\nPayouts arrive two business days later.", n=2, title="Payouts"),
    ]
    answer = extractive_answer("How long after a charge can I issue a refund?", sources)
    assert answer.confident
    assert answer.text == "Refunds can be issued up to 180 days after the original charge. [1]"


def test_says_so_when_the_passages_do_not_cover_the_question() -> None:
    answer = extractive_answer("What is the capital of France?", [hit("Payouts are daily.", n=1)])
    assert not answer.confident
    assert answer.text.startswith(NOT_FOUND)
    assert "[1]" in answer.text


def test_the_sentence_window_is_what_gets_answered_from() -> None:
    windowed = hit(
        "Respond within 7 days.",
        context="Disputes\n\nRespond within 7 days. Late responses lose the dispute automatically.",
        n=1,
        title="Disputes",
    )
    answer = extractive_answer("What happens to late dispute responses?", [windowed])
    assert "Late responses lose the dispute automatically." in answer.text


def test_list_items_travel_with_their_siblings() -> None:
    passage = (
        "Supported events\n\n\N{BULLET} payment.succeeded fires when a charge settles\n\n"
        "\N{BULLET} payment.failed fires when a charge is declined\n\n"
        "\N{BULLET} refund.created fires when a refund is issued"
    )
    answer = extractive_answer("Which events are supported?", [hit(passage, n=1)])
    assert answer.text.count("\n- ") == 2


def test_meaning_breaks_ties_between_lexically_equal_units() -> None:
    sources = [hit("Uptime is reported monthly. Availability is committed at 99.95 percent.", n=1)]
    units = answer_units(sources)
    answer = extractive_answer(
        "What availability is committed?",
        sources,
        units=units,
        similarities=np.array([0.1, 0.9], dtype=np.float32),
    )
    assert answer.text.startswith("Availability is committed at 99.95 percent.")


def test_valid_markers_become_citations_and_invalid_ones_disappear() -> None:
    sources = [
        hit("Refund window is 180 days. Fees are kept.", n=1, title="Refunds", location="Policy"),
        hit("Payouts arrive in 2 days.", n=2, title="Payouts", location="Schedule"),
    ]
    text, citations = extract_citations("Refunds: 180 days [1]. Payouts: 2 days [2][7].", sources)
    assert text == "Refunds: 180 days [1]. Payouts: 2 days [2]."
    assert [c["n"] for c in citations] == [1, 2]
    assert citations[0]["quote"] == "Refund window is 180 days."
    assert citations[1]["external_id"] == "payouts"


def test_best_quote_prefers_the_supporting_sentence() -> None:
    passage = "Hotels are capped. Payouts arrive two days after capture. Flights are economy."
    assert best_quote("payouts arrive after two days", passage) == (
        "Payouts arrive two days after capture."
    )


def test_phrases_and_table_values_win_over_scattered_words() -> None:
    table = hit(
        "Default limits\n\nMode: Live mode; Requests per second: 100\n\n"
        "Mode: Test mode; Requests per second: 25\n\nMode: Search endpoints; Requests per second: 20",
        n=1,
        title="Rate limits",
    )
    load = hit(
        "Load testing\n\nLoad test in test mode instead, keeping in mind that test mode allows 25 "
        "requests per second.",
        n=2,
        title="Rate limits",
    )
    answer = extractive_answer(
        "How many requests per second are allowed in live mode?", [table, load]
    )
    assert "Mode: Live mode; Requests per second: 100 [1]" in answer.text.splitlines()[0]
    assert "Search endpoints" not in answer.text


def test_how_long_asks_for_a_duration_not_for_the_word_long() -> None:
    passage = (
        "Refunds\n\nYou can issue several partial refunds as long as their total does not exceed "
        "the charge. Refunds usually take 5 to 10 business days to appear on the customer's "
        "statement."
    )
    answer = extractive_answer(
        "How long do refunds take to reach the customer?", [hit(passage, n=1)]
    )
    assert answer.text.startswith("Refunds usually take 5 to 10 business days")


def test_codes_and_the_retrievers_ranking_pick_the_source() -> None:
    limits = hit("Requests over the limit fail with HTTP 429.", n=1, title="Rate limits", fused=0.9)
    keys = hit(
        "A retry within 24 hours returns the saved response.",
        n=2,
        title="Idempotency keys",
        fused=0.1,
    )
    answer = extractive_answer("How should I retry a request that returned 429?", [limits, keys])
    assert answer.text.startswith("Requests over the limit fail with HTTP 429. [1]")


def test_one_generic_title_word_does_not_name_a_document() -> None:
    limits = hit("Requests over the limit fail with HTTP 429.", n=1, title="Rate limits", fused=0.9)
    idempotency = hit(
        "Retried requests with the same key return the saved response.",
        n=2,
        title="Idempotent requests",
        fused=0.2,
    )
    answer = extractive_answer("Why do requests fail with 429?", [limits, idempotency])
    assert answer.text.startswith("Requests over the limit fail with HTTP 429. [1]")


def test_sentences_about_the_page_itself_do_not_answer() -> None:
    passage = (
        "Payouts\n\nThis page explains when payouts arrive and what to do when one fails. "
        "A failed payout returns the funds to your balance within 2 to 5 business days."
    )
    answer = extractive_answer("What happens when a payout fails?", [hit(passage, n=1)])
    assert answer.text.startswith("A failed payout returns the funds")
