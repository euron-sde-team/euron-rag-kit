"""Merging the vector and keyword candidate lists into one ranking.

- Reciprocal Rank Fusion needs no score calibration between the two systems: an item's
  score is the sum of weight / (k + rank) over the lists it appears in.
- Weighted fusion is a convex combination of min-max normalised scores. It keeps the
  margin information RRF throws away, at the price of being sensitive to outliers.

With `vector_weight = w`, RRF weights the lists 2w and 2(1 - w), so w = 0.5 is standard RRF.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

RRF_K = 60


def reciprocal_rank_fusion(
    vector: Sequence[uuid.UUID],
    keyword: Sequence[uuid.UUID],
    *,
    k: int = RRF_K,
    vector_weight: float = 0.5,
) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for weight, ranking in ((2 * vector_weight, vector), (2 * (1 - vector_weight), keyword)):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
    return scores


def min_max(scores: Mapping[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    if high - low < 1e-12:
        return dict.fromkeys(scores, 1.0)
    return {item: (value - low) / (high - low) for item, value in scores.items()}


def weighted_fusion(
    vector: Mapping[uuid.UUID, float],
    keyword: Mapping[uuid.UUID, float],
    *,
    vector_weight: float = 0.5,
) -> dict[uuid.UUID, float]:
    v, kw = min_max(vector), min_max(keyword)
    return {
        item: vector_weight * v.get(item, 0.0) + (1 - vector_weight) * kw.get(item, 0.0)
        for item in v.keys() | kw.keys()
    }


def ranked(scores: Mapping[uuid.UUID, float]) -> list[uuid.UUID]:
    """Highest score first; ties broken by id so a ranking is reproducible."""
    return sorted(scores, key=lambda item: (-scores[item], str(item)))
