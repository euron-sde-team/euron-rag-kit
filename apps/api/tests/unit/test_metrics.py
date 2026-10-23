import math

import pytest

from ragkit_server.evaluation.metrics import (
    answer_correctness,
    claims,
    faithfulness,
    is_refusal,
    retrieval_metrics,
)
from ragkit_server.evaluation.relevance import (
    ExpectedSource,
    RetrievedChunk,
    evidence_matches,
    judge,
)

EXPECTED = [
    ExpectedSource("webhooks", "Reject events older than five minutes"),
    ExpectedSource("rate-limits"),
]


def chunks(*pairs: tuple[str, str]) -> list[RetrievedChunk]:
    return [RetrievedChunk(external_id, passage) for external_id, passage in pairs]


def test_evidence_matching_tolerates_case_punctuation_and_small_edits() -> None:
    passage = "Verify the signature.\n\nReject events older than five (5) minutes, always."
    assert evidence_matches("reject events older than five minutes", passage)
    assert evidence_matches("Events older than five minutes are rejected", passage)
    assert not evidence_matches("Retries continue for three days", passage)


def test_relevance_needs_the_right_document_and_the_evidence() -> None:
    retrieved = chunks(
        ("webhooks", "Webhooks are sent as JSON."),
        ("payouts", "Reject events older than five minutes."),
        ("webhooks", "Reject events older than five minutes."),
        ("rate-limits", "Live mode allows 100 requests per second."),
    )
    judgement = judge(retrieved, EXPECTED)
    assert judgement.relevant == [False, False, True, True]
    assert judgement.covers[3] == frozenset({1})


def test_retrieval_metrics_by_hand() -> None:
    # Relevant at ranks 3 and 4, each covering a different expected source, k = 5.
    judgement = judge(
        chunks(
            ("payouts", "a"),
            ("payouts", "b"),
            ("webhooks", "Reject events older than five minutes."),
            ("rate-limits", "Live mode allows 100 requests per second."),
            ("payouts", "c"),
        ),
        EXPECTED,
    )
    m = retrieval_metrics(judgement, k=5)
    assert m["hit_rate"] == 1.0
    assert m["context_recall"] == 1.0
    assert m["mrr"] == pytest.approx(1 / 3)
    assert m["context_precision"] == pytest.approx((1 / 3 + 2 / 4) / 2)
    ideal = 1 + 1 / math.log2(3)
    assert m["ndcg"] == pytest.approx((1 / math.log2(4) + 1 / math.log2(5)) / ideal)


def test_repeat_coverage_earns_no_extra_gain() -> None:
    judgement = judge(
        chunks(
            ("rate-limits", "Limits."),
            ("rate-limits", "More limits."),
        ),
        [ExpectedSource("rate-limits")],
    )
    m = retrieval_metrics(judgement, k=2)
    assert m["ndcg"] == pytest.approx(1.0)
    assert m["context_precision"] == pytest.approx(1.0)


def test_nothing_relevant_scores_zero_and_k_truncates() -> None:
    judgement = judge(chunks(("payouts", "x"), ("rate-limits", "Limits.")), EXPECTED)
    assert retrieval_metrics(judgement, k=1) == {
        "hit_rate": 0.0,
        "context_recall": 0.0,
        "context_precision": 0.0,
        "mrr": 0.0,
        "ndcg": 0.0,
    }
    assert retrieval_metrics(judgement, k=2)["context_recall"] == 0.5


def test_faithfulness_checks_numbers_and_word_support() -> None:
    contexts = ["Refunds can be issued up to 180 days after the original charge."]
    assert (
        faithfulness("Refunds can be issued up to 180 days after the charge [1].", contexts) == 1.0
    )
    assert faithfulness("Refunds can be issued up to 365 days after the charge.", contexts) == 0.0
    mixed = (
        "Refunds can be issued up to 180 days after the charge. Disputes cost fifteen dollars each."
    )
    assert faithfulness(mixed, contexts) == 0.5
    assert (
        faithfulness("I could not find a clear answer to that in the retrieved passages.", contexts)
        == 1.0
    )


def test_claims_skip_fillers_and_split_lists() -> None:
    answer = "Yes.\n- Refunds take five business days [1].\n- Payouts arrive two days later [2]."
    assert claims(answer) == ["Refunds take five business days.", "Payouts arrive two days later."]


def test_correctness_rewards_facts_and_tolerates_extra_words() -> None:
    reference = "Live mode allows 100 requests per second."
    exact = answer_correctness("Live mode allows 100 requests per second [1].", reference)
    verbose = answer_correctness(
        "In live mode the API allows 100 requests per second, and test mode allows 25 [1].",
        reference,
    )
    wrong_number = answer_correctness("Live mode allows 50 requests per second.", reference)
    assert exact == pytest.approx(1.0)
    assert 0.6 < verbose < exact
    assert wrong_number < 0.6
    assert answer_correctness("I could not find a clear answer to that.", reference) == 0.0


def test_identifiers_count_as_facts() -> None:
    reference = "Send the Idempotency-Key header."
    assert answer_correctness("Use the Idempotency-Key header on POST requests.", reference) > 0.8
    assert answer_correctness("Use a unique header on POST requests.", reference) < 0.5


def test_refusals_are_recognised() -> None:
    assert is_refusal("The sources do not answer this question.")
    assert is_refusal("")
    assert not is_refusal("Refunds take five days.")
