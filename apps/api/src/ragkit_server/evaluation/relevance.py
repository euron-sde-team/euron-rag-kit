"""Which retrieved chunks are relevant to a question, judged by evidence, not by chunk id.

An expected source names a document (by external id) and, optionally, evidence: text the
answer depends on. A chunk *covers* an expected source when it comes from that document and
its passage contains the evidence. Containment is checked after normalisation (case,
punctuation, whitespace) as a substring, or as at least 80% of the evidence's stemmed
content words occurring in the passage, which tolerates small edits such as a heading or a
line break falling inside the quote.

Because nothing depends on chunk ids, runs over different chunking strategies (fixed
windows, structure-aware chunks, sentence windows) are measured on the same footing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ragkit_server.core.text import content_terms, normalize_for_match

EVIDENCE_TERM_COVERAGE = 0.8


@dataclass(frozen=True, slots=True)
class ExpectedSource:
    document: str
    evidence: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    external_id: str
    passage: str


@dataclass(frozen=True, slots=True)
class Judgement:
    """For each retrieved chunk, the indexes of the expected sources it covers."""

    covers: tuple[frozenset[int], ...]
    expected: int

    @property
    def relevant(self) -> list[bool]:
        return [bool(c) for c in self.covers]


def evidence_matches(evidence: str, passage: str) -> bool:
    needle = normalize_for_match(evidence)
    if not needle:
        return True
    if needle in normalize_for_match(passage):
        return True
    wanted = set(content_terms(evidence))
    if not wanted:
        return False
    present = wanted & set(content_terms(passage))
    return len(present) / len(wanted) >= EVIDENCE_TERM_COVERAGE


def judge(retrieved: Sequence[RetrievedChunk], expected: Sequence[ExpectedSource]) -> Judgement:
    covers = []
    for chunk in retrieved:
        covered = frozenset(
            index
            for index, source in enumerate(expected)
            if source.document == chunk.external_id
            and (source.evidence is None or evidence_matches(source.evidence, chunk.passage))
        )
        covers.append(covered)
    return Judgement(covers=tuple(covers), expected=len(expected))
