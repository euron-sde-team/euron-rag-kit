"""Retrieval and answer metrics for one question. Every function is deterministic.

Retrieval metrics read a `Judgement` of the top k chunks (see relevance.py); `rel_i` is 1
when chunk i covers at least one expected source.

- hit_rate: 1 if any chunk is relevant.
- context_recall: the share of expected sources covered by any chunk.
- context_precision: average precision over the relevant positions,
  sum(precision@i * rel_i) / sum(rel_i).
- mrr: 1 / rank of the first relevant chunk.
- ndcg: gain 1 where a chunk covers an expected source not covered above it, discounted by
  log2(i + 1), divided by the ideal DCG of min(k, R) gains at the top.

Answer metrics compare text:

- faithfulness: the share of the answer's claim sentences supported by the context: every
  number in the claim appears in the context, and the best single passage contains at least
  70% of the claim's content words. An answer with no claims (a refusal) scores 1.
- answer_correctness: against the reference answer, 0.5 * F2 + 0.5 * fact recall when the
  reference holds facts (numbers, identifiers), F2 alone otherwise. F2 is the recall-weighted
  F-score over stemmed content words. A refusal scores 0.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from ragkit_server.core.text import (
    content_terms,
    identifiers,
    normalize_for_match,
    numbers,
    split_sentences,
)
from ragkit_server.evaluation.relevance import Judgement

RETRIEVAL_METRICS = ("hit_rate", "context_recall", "context_precision", "mrr", "ndcg")
ANSWER_METRICS = ("faithfulness", "answer_correctness")
METRICS = (*RETRIEVAL_METRICS, *ANSWER_METRICS)
CLAIM_SUPPORT = 0.7
MIN_CLAIM_TERMS = 3
_MARKER = re.compile(r"\s?\[\d{1,2}(?:\s*[,;]\s*\d{1,2})*\]")
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
_REFUSALS = (
    "i could not find",
    "the sources do not answer",
    "the sources don t answer",
    "the context does not",
    "not covered by the sources",
    "cannot answer",
)


def retrieval_metrics(judgement: Judgement, k: int) -> dict[str, float]:
    relevant = judgement.relevant[:k]
    covers = judgement.covers[:k]
    expected = judgement.expected
    hits = sum(relevant)
    covered = set().union(*covers) if covers else set()

    precision_sum = 0.0
    seen = 0
    for position, is_relevant in enumerate(relevant, start=1):
        if is_relevant:
            seen += 1
            precision_sum += seen / position
    first = next((i for i, r in enumerate(relevant, start=1) if r), None)

    dcg = 0.0
    novel: set[int] = set()
    for position, cover in enumerate(covers, start=1):
        if cover - novel:
            dcg += 1.0 / math.log2(position + 1)
            novel |= cover
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(k, expected) + 1))

    return {
        "hit_rate": 1.0 if hits else 0.0,
        "context_recall": len(covered) / expected if expected else 0.0,
        "context_precision": precision_sum / hits if hits else 0.0,
        "mrr": 1.0 / first if first else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
    }


def strip_citations(text: str) -> str:
    return _MARKER.sub("", text).strip()


def is_refusal(answer: str) -> bool:
    opening = normalize_for_match(answer)[:160]
    return not opening or any(marker in opening for marker in _REFUSALS)


def claims(answer: str) -> list[str]:
    """Checkable sentences: list items and sentences with at least three content words."""
    found: list[str] = []
    for line in strip_citations(answer).split("\n"):
        line = _BULLET.sub("", line).strip()
        found.extend(
            sentence
            for sentence in split_sentences(line) or ([line] if line else [])
            if len(set(content_terms(sentence))) >= MIN_CLAIM_TERMS
        )
    return found


def faithfulness(answer: str, contexts: Sequence[str]) -> float:
    if is_refusal(answer):
        return 1.0
    statements = claims(answer)
    if not statements:
        return 1.0
    passage_terms = [set(content_terms(context)) for context in contexts]
    context_numbers = {n for context in contexts for n in numbers(context)}
    supported = 0
    for statement in statements:
        terms = set(content_terms(statement))
        if any(n not in context_numbers for n in numbers(statement)):
            continue
        best = max((len(terms & p) / len(terms) for p in passage_terms), default=0.0)
        if best >= CLAIM_SUPPORT:
            supported += 1
    return supported / len(statements)


def _f2(answer_terms: list[str], reference_terms: list[str]) -> float:
    overlap = sum((Counter(answer_terms) & Counter(reference_terms)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(answer_terms)
    recall = overlap / len(reference_terms)
    return 5 * precision * recall / (4 * precision + recall)


def answer_correctness(answer: str, reference: str) -> float:
    if is_refusal(answer):
        return 0.0
    text = strip_citations(answer)
    reference_terms = content_terms(reference)
    if not reference_terms:
        return 1.0 if normalize_for_match(reference) in normalize_for_match(text) else 0.0
    f2 = _f2(content_terms(text), reference_terms)
    answer_numbers = set(numbers(text))
    answer_identifiers = set(identifiers(text))
    lowered = text.lower()
    facts = [("n", value) for value in numbers(reference)]
    facts += [("i", value) for value in identifiers(reference)]
    if not facts:
        return f2
    found = sum(
        1
        for kind, value in facts
        if (
            value in answer_numbers
            if kind == "n"
            else value in answer_identifiers or value in lowered
        )
    )
    return 0.5 * f2 + 0.5 * found / len(facts)
