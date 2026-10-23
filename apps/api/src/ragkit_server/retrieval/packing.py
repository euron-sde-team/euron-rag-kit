"""Packing retrieved hits into an answerer's context budget."""

from __future__ import annotations

from collections.abc import Sequence

from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.retrieval.types import Hit


def pack_context(
    hits: Sequence[Hit], counter: TokenCounter, *, budget: int, max_sources: int
) -> list[Hit]:
    """Greedy fill of the token budget in rank order, numbered from 1 for citation.

    The best hit is always included, even when it alone exceeds the budget: an answer from
    one long passage beats no answer.
    """
    packed: list[Hit] = []
    used = 0
    for hit in hits:
        if len(packed) >= max_sources:
            break
        cost = counter.count(hit.passage)
        if packed and used + cost > budget:
            continue
        packed.append(hit)
        used += cost
    for number, hit in enumerate(packed, start=1):
        hit.n = number
    return packed
