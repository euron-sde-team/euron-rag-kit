"""The offline answerer: composes an answer from the retrieved passages' own sentences.

No model call, no network, deterministic. Retrieved passages are broken into answer
units (sentences, bullet items and table records; headings become context, not
candidates). Each unit is scored against the question by:

- lexical coverage: IDF-weighted share of the question's terms the unit contains, with
  half credit for terms in its heading and a quarter for terms in its document's title,
- meaning: cosine similarity between the unit and the question, when embeddings are given,
- phrases: a bonus for every pair of consecutive question words the unit repeats in order,
  so "live mode" beats a sentence that has "live" and "mode" apart,
- the retrieval stage's own judgment: a boost in proportion to the source's score against
  the best source, so a sentence from the passage the reranker put first beats a sentence
  with the same words from a passage it ranked far lower,
- small boosts for numbers when the question asks for one; a penalty for sentences that
  describe the document instead of saying something ("This page explains...").

The best units are kept, list items travel with their siblings, and everything is put back
in document order and cited. When nothing covers the question well enough, it says so and
points at the closest passage instead of guessing.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from ragkit_server.core.text import content_terms, split_sentences
from ragkit_server.retrieval.types import Hit

_NUMERIC_INTENT = re.compile(
    r"\b(how (much|many|long|often|quickly|fast)|what (percent|percentage|share)|when|cost|"
    r"price|budget|revenue|rate|total|number|amount|salary|limit|deadline|date|days|hours|"
    r"weeks|uptime)\b",
    re.IGNORECASE,
)
_HAS_NUMBER = re.compile(r"\d")
_RECORD = re.compile(r"^[^:;]{1,60}: [^;]+(; [^:;]{1,60}: [^;]+)+$")
_SUPERLATIVE = re.compile(
    r"\b(best|highest|most|largest|biggest|top|greatest|maximum|lowest|least|fewest|smallest|worst|minimum)\b",
    re.IGNORECASE,
)
_LOW = frozenset({"lowest", "least", "fewest", "smallest", "worst", "minimum"})
_NUMBER = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_LIST_PREFIX = ("\N{BULLET}", "- ", "* ")
_TERMINAL = (".", "!", "?", ":", ";", ")", '"', "'")
# "How long", "how often": the second word asks for a kind of answer; it is not a word to
# look for ("as long as" says nothing about duration).
_QUESTION_FORM = re.compile(r"\bhow (long|often|soon|fast|quickly|far)\b", re.IGNORECASE)
# Sentences about the document itself: "This page explains...", "This Service Level
# Agreement (SLA) describes...". They match a question's words without answering it.
_META = re.compile(
    r"^(this|the following|in this)\b[^.]{0,80}?\b(describes|explains|covers|outlines|lists|"
    r"shows|summari[sz]es|walks you)\b",
    re.IGNORECASE,
)
NOT_FOUND = "I could not find a clear answer to that in the retrieved passages."
PHRASE_BONUS = 0.04
PHRASE_CAP = 0.16
RANK_PRIOR = 0.3
# Numbers and codes in a question ("429", "ACME-4011") are the most specific words in it.
IDENTIFIER_WEIGHT = 1.5
META_PENALTY = 0.6


@dataclass(frozen=True, slots=True)
class ExtractiveAnswer:
    text: str
    confident: bool
    used: tuple[int, ...]


@dataclass(slots=True)
class Unit:
    text: str
    source: Hit
    heading: str
    order: int
    is_item: bool
    terms: frozenset[str]
    context_terms: frozenset[str]
    title_terms: frozenset[str]
    # Consecutive word pairs, for phrase matches.
    bigrams: frozenset[tuple[str, str]] = frozenset()
    # The words that tell this unit apart: for a table record, its values; every row of a
    # table repeats the column names, so they must not make two rows look the same.
    distinct: frozenset[str] = frozenset()
    lexical: float = 0.0
    score: float = 0.0


def _is_heading(block: str) -> bool:
    if "\n" in block or block.startswith(_LIST_PREFIX) or _RECORD.match(block):
        return False
    words = len(block.split())
    # FAQ-style headings are questions; they label the answer below them.
    return (words <= 9 and not block.endswith(_TERMINAL)) or (words <= 14 and block.endswith("?"))


def _clean(text: str, *, record: bool = False) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.lstrip("\N{BULLET}*-").strip()
    if text and not record and text[-1] not in ".!?:)\"'%":
        text += "."
    return text


def answer_units(sources: Sequence[Hit]) -> list[Unit]:
    """Split passages into answerable units, each remembering the heading above it."""
    units: list[Unit] = []
    for source in sources:
        heading = source.heading.split(" > ")[-1] if source.heading else ""
        title_terms = frozenset(content_terms(source.document_title))
        for block in source.passage.split("\n\n"):
            block = block.strip()
            if not block or block.startswith("Columns: "):
                continue
            if _is_heading(block):
                heading = block
                continue
            record = bool(_RECORD.match(block))
            is_item = record or block.startswith(_LIST_PREFIX)
            pieces = [block] if is_item else split_sentences(block) or [block]
            for piece in pieces:
                text = _clean(piece, record=record)
                if len(text.split()) < 3:
                    continue
                words = content_terms(text)
                values = (
                    frozenset(content_terms(" ".join(v for _, v in _fields(text))))
                    if record
                    else frozenset(words)
                )
                units.append(
                    Unit(
                        text=text,
                        source=source,
                        heading=heading,
                        order=len(units),
                        is_item=is_item,
                        terms=frozenset(words),
                        context_terms=frozenset(content_terms(heading)),
                        title_terms=title_terms,
                        bigrams=frozenset(pairwise(words)),
                        distinct=values or frozenset(words),
                    )
                )
    return units


def extractive_answer(
    question: str,
    sources: Sequence[Hit],
    *,
    units: list[Unit] | None = None,
    similarities: np.ndarray | None = None,
    max_units: int = 5,
) -> ExtractiveAnswer:
    units = units if units is not None else answer_units(sources)
    query_terms = set(content_terms(question))
    query_bigrams = set(pairwise(content_terms(question)))
    if not units or not query_terms:
        return _not_found(sources)

    superlative_words = {w.lower() for w in _SUPERLATIVE.findall(question)}
    query_terms -= superlative_words
    query_terms -= set(content_terms(" ".join(_QUESTION_FORM.findall(question))))
    if not query_terms:
        return _not_found(sources)

    frequency = Counter(term for unit in units for term in unit.terms | unit.context_terms)
    total = len(units)
    default_idf = math.log(1 + total)
    idf = {term: math.log(1 + total / (1 + count)) for term, count in frequency.items()}
    # Words that name a document ("the Globex agreement") pick the document; the remaining
    # words say what to find in it, so they carry most of the weight.
    title_words = {term for unit in units for term in unit.title_terms}
    weight = {
        t: idf.get(t, default_idf)
        * (0.4 if t in title_words else 1.0)
        * (IDENTIFIER_WEIGHT if _HAS_NUMBER.search(t) else 1.0)
        for t in query_terms
    }
    query_weight = sum(weight.values()) or 1.0
    wants_number = bool(_NUMERIC_INTENT.search(question))

    def coverage(terms: frozenset[str]) -> float:
        return sum(weight[t] for t in terms & query_terms)

    # Meaning breaks ties between lexically similar units; centred raw similarity keeps it
    # from overruling a clear lexical match the way min-max scaling would.
    semantic = np.zeros(len(units), dtype=np.float32)
    if similarities is not None and len(similarities) == len(units):
        semantic = (similarities - float(similarities.mean())).astype(np.float32)

    # When the question names a document ("the Globex agreement", "release 4.2"), prefer
    # units from the document(s) whose title carries all of those words.
    named = {t for t in query_terms if t in title_words}
    targeted: set[object] = set()
    if named:
        titles = {unit.source.document_id: unit.title_terms for unit in units}

        def names(title: frozenset[str]) -> bool:
            # One shared generic word ("requests" in "Idempotent requests") does not name a
            # document; its whole title, two of its words or a number in it ("4.2") does.
            matched = named & title
            return bool(matched) and (
                matched == title or len(matched) >= 2 or any(_HAS_NUMBER.search(t) for t in matched)
            )

        hits = {
            doc: sum(weight[t] for t in named & title)
            for doc, title in titles.items()
            if names(title)
        }
        best_hit = max(hits.values(), default=0.0)
        if hits and best_hit >= sum(weight[t] for t in named) * 0.99:
            targeted = {doc for doc, hit in hits.items() if hit >= best_hit}

    # Scores of different stages are not comparable across requests, but within one request
    # the ratio to the best source says how much more the retriever trusted it.
    best_source = max((unit.source.score for unit in units), default=0.0)

    for index, unit in enumerate(units):
        covered = coverage(unit.terms)
        context = coverage(unit.context_terms - unit.terms)
        title = coverage(unit.title_terms - unit.terms - unit.context_terms)
        unit.lexical = min(1.0, (covered + 0.5 * context + 0.25 * title) / query_weight)
        score = unit.lexical + 0.5 * float(semantic[index])
        if unit.source.document_id in targeted:
            score += 0.15
        score += min(PHRASE_CAP, PHRASE_BONUS * len(unit.bigrams & query_bigrams))
        if wants_number and _HAS_NUMBER.search(unit.text):
            score += 0.1
        if best_source > 0:
            score += RANK_PRIOR * max(0.0, unit.source.score) / best_source
        if unit.source.n:
            score += 0.05 / unit.source.n
        if len(unit.text.split()) > 70:
            score *= 0.85
        if _META.match(unit.text):
            score *= META_PENALTY
        unit.score = score

    if superlative_words:
        superlative = _superlative(question, units, query_terms)
        if superlative is not None:
            return superlative

    if max(u.lexical for u in units) < 0.25:
        return _not_found(sources)

    ranked = sorted(units, key=lambda u: u.score, reverse=True)
    if targeted:
        # A named document answers first; other documents only fill in around it.
        ranked = [u for u in ranked if u.source.document_id in targeted] + [
            u for u in ranked if u.source.document_id not in targeted
        ]
    best = ranked[0]

    # A heading that matches the question ("How do I reset an Atlas robot?") means the
    # section under it is the answer: return it whole, in order.
    if best.heading and coverage(best.context_terms) / query_weight >= 0.5:
        section = [u for u in units if u.source is best.source and u.heading == best.heading]
        return _compose(section[:max_units])

    # Extra units must carry a question term that is not common across the passages, so
    # "Atlas v2" alone does not pull every sentence about Atlas into an answer about payload.
    present = sorted(weight[t] for t in query_terms if t in frequency)
    floor = present[len(present) // 2] if present else 0.0
    informative = {t for t in query_terms if weight[t] >= floor}
    section_match = bool(best.context_terms & query_terms)
    bullet = best.text and best.is_item and not _RECORD.match(best.text)

    chosen: list[Unit] = [best]
    for unit in ranked[1:]:
        if len(chosen) >= max_units:
            break
        same_section = unit.source is best.source and unit.heading == best.heading
        is_bullet = unit.is_item and not _RECORD.match(unit.text)
        sibling = is_bullet and same_section and (bullet or section_match)
        if targeted and unit.source.document_id not in targeted:
            continue
        if sibling:
            if unit.score < best.score * 0.4:
                continue
        elif (
            unit.score < best.score * 0.7
            or unit.lexical < best.lexical * 0.6
            or not (unit.distinct & informative)
        ):
            continue
        if any(_overlap(unit.distinct, other.distinct) > 0.6 for other in chosen):
            continue
        chosen.append(unit)

    return _compose(chosen)


def _compose(chosen: list[Unit], lead: str | None = None) -> ExtractiveAnswer:
    chosen = sorted(chosen, key=lambda u: (u.source.n, u.order))
    lines = [f"{unit.text} [{unit.source.n}]" for unit in chosen]
    if lead:
        lines.insert(0, lead)
    items = sum(unit.is_item for unit in chosen)
    text = (
        "\n".join(f"- {line}" for line in lines)
        if len(lines) >= 3 or items >= 2
        else " ".join(lines)
    )
    return ExtractiveAnswer(
        text=text, confident=True, used=tuple(dict.fromkeys(u.source.n for u in chosen))
    )


def _fields(text: str) -> list[tuple[str, str]]:
    pairs = []
    for part in text.split("; "):
        key, _, value = part.partition(": ")
        if value:
            pairs.append((key.strip(), value.strip()))
    return pairs


def _number(value: str) -> float | None:
    match = _NUMBER.search(value.replace("$", ""))
    if match is None:
        return None
    try:
        number = float(match.group().replace(",", ""))
    except ValueError:
        return None
    suffix = value[match.end() : match.end() + 1].upper()
    return number * {"K": 1e3, "M": 1e6, "B": 1e9}.get(suffix, 1)


def _superlative(
    question: str, units: list[Unit], query_terms: set[str]
) -> ExtractiveAnswer | None:
    """ "Which site had the best pick rate?": compare one numeric column across table rows."""
    match = _SUPERLATIVE.search(question)
    if match is None:
        return None
    records = [u for u in units if _RECORD.match(u.text)]
    best_field, best_overlap = None, 0
    for unit in records:
        for key, value in _fields(unit.text):
            overlap = len(set(content_terms(key)) & query_terms)
            if overlap > best_overlap and _number(value) is not None:
                best_field, best_overlap = key, overlap
    if best_field is None:
        return None
    scored = [
        (number, unit)
        for unit in records
        for key, value in _fields(unit.text)
        if key == best_field and (number := _number(value)) is not None
    ]
    if len(scored) < 2:
        return None
    low = match.group(1).lower() in _LOW
    number, winner = (min if low else max)(scored, key=lambda item: item[0])
    label = _fields(winner.text)[0][1]
    value = dict(_fields(winner.text))[best_field]
    direction = "lowest" if low else "highest"
    lead = f"{label} has the {direction} {best_field.lower()}: {value} [{winner.source.n}]."
    return _compose([winner], lead=lead)


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _not_found(sources: Sequence[Hit]) -> ExtractiveAnswer:
    if not sources:
        return ExtractiveAnswer(text=NOT_FOUND, confident=False, used=())
    top = sources[0]
    text = f"{NOT_FOUND} The closest passage is in {top.document_title} ({top.location}) [{top.n}]."
    return ExtractiveAnswer(text=text, confident=False, used=(top.n,))
