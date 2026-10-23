import uuid

import pytest

from ragkit_server.retrieval.fusion import min_max, ranked, reciprocal_rank_fusion, weighted_fusion

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def test_rrf_rewards_agreement_between_lists() -> None:
    scores = reciprocal_rank_fusion([A, B, C], [C, A, D])
    assert ranked(scores)[:2] == [A, C]
    assert scores[A] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[D] == pytest.approx(1 / 63)


def test_rrf_vector_weight_shifts_the_balance() -> None:
    vector_heavy = reciprocal_rank_fusion([A], [B], vector_weight=0.8)
    keyword_heavy = reciprocal_rank_fusion([A], [B], vector_weight=0.2)
    assert ranked(vector_heavy)[0] == A
    assert ranked(keyword_heavy)[0] == B


def test_weighted_fusion_normalises_each_list() -> None:
    vector = {A: 0.9, B: 0.5, C: 0.1}
    keyword = {B: 12.0, C: 2.0}
    fused = weighted_fusion(vector, keyword, vector_weight=0.5)
    assert fused[A] == pytest.approx(0.5)  # best vector score, absent from keyword
    assert fused[B] == pytest.approx(0.5 * 0.5 + 0.5 * 1.0)
    assert fused[C] == pytest.approx(0.0)
    assert ranked(fused) == [B, A, C]


def test_min_max_handles_ties_and_empty_lists() -> None:
    assert min_max({}) == {}
    assert min_max({A: 3.0, B: 3.0}) == {A: 1.0, B: 1.0}


def test_ranking_is_reproducible_on_ties() -> None:
    assert ranked({B: 1.0, A: 1.0, C: 2.0}) == [C, A, B]
