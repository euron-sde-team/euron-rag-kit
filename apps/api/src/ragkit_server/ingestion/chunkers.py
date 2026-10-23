"""Three chunking strategies behind one function.

- **fixed**: the whole document as one stream, cut into token windows with overlap. Ignores
  structure on purpose; it is the baseline the other strategies are measured against.
- **recursive**: structure first. Chunks never cross a section; blocks are packed up to the
  target, an oversized block splits at sentences and an oversized sentence at words.
  Consecutive chunks overlap by whole units, and a heading never ends a chunk: it moves
  forward to the text it introduces.
- **sentence_window**: small retrieval units (a sentence or two) that each carry a wider
  window of surrounding sentences as `context`, for the answerer and the relevance judge.

Every chunk's `text` is an exact slice of its section's cleaned text (of the document's
stream for `fixed`), so offsets can be shown and checked.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.core.text import sentence_spans
from ragkit_server.ingestion.types import BLOCK_SEPARATOR, ParsedSection

Strategy = Literal["fixed", "recursive", "sentence_window"]
SECTION_SEPARATOR = "\n\n"
MIN_SENTENCE_WORDS = 5
_WORD = re.compile(r"\S+")


@dataclass(frozen=True, slots=True)
class ChunkingOptions:
    strategy: Strategy = "recursive"
    chunk_tokens: int = 300
    overlap_tokens: int = 40
    sentences_per_chunk: int = 2
    window_sentences: int = 2


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    section_ordinal: int
    ordinal: int
    heading: str
    location: str
    text: str
    # The text an answerer should read, when wider than `text` (sentence windows).
    context: str | None
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True, slots=True)
class _Unit:
    start: int
    end: int
    tokens: int
    is_heading: bool
    path: tuple[str, ...]


def chunk_sections(
    sections: Sequence[ParsedSection], counter: TokenCounter, options: ChunkingOptions
) -> list[ChunkDraft]:
    if options.strategy == "fixed":
        return _fixed(sections, counter, options)
    if options.strategy == "sentence_window":
        return _sentence_window(sections, counter, options)
    return _recursive(sections, counter, options)


def _has_body(section: ParsedSection) -> bool:
    return any(block.heading_level is None and block.text.strip() for block in section.blocks)


# Fixed windows ------------------------------------------------------------------------------


def _fixed(
    sections: Sequence[ParsedSection], counter: TokenCounter, options: ChunkingOptions
) -> list[ChunkDraft]:
    parts: list[str] = []
    starts: list[int] = []
    owners: list[int] = []
    position = 0
    for ordinal, section in enumerate(sections):
        if not _has_body(section):
            continue
        if parts:
            position += len(SECTION_SEPARATOR)
        starts.append(position)
        owners.append(ordinal)
        parts.append(section.text)
        position += len(section.text)
    stream = SECTION_SEPARATOR.join(parts)
    chunks: list[ChunkDraft] = []
    for start, end in counter.windows(stream, options.chunk_tokens, options.overlap_tokens):
        owner = owners[max(0, bisect.bisect_right(starts, start) - 1)]
        body = stream[start:end]
        chunks.append(
            ChunkDraft(
                section_ordinal=owner,
                ordinal=len(chunks),
                heading="",
                location=sections[owner].label,
                text=body,
                context=None,
                char_start=start,
                char_end=end,
                token_count=counter.count(body),
            )
        )
    return chunks


# Recursive by structure ---------------------------------------------------------------------


def _recursive(
    sections: Sequence[ParsedSection], counter: TokenCounter, options: ChunkingOptions
) -> list[ChunkDraft]:
    target = options.chunk_tokens
    overlap = min(options.overlap_tokens, target // 2)
    chunks: list[ChunkDraft] = []
    for ordinal, section in enumerate(sections):
        if not _has_body(section):
            continue
        text = section.text
        for start, end, heading in _pack(_units(section, counter, target), target, overlap):
            body = text[start:end]
            chunks.append(
                ChunkDraft(
                    section_ordinal=ordinal,
                    ordinal=len(chunks),
                    heading=heading,
                    location=section.label,
                    text=body,
                    context=None,
                    char_start=start,
                    char_end=end,
                    token_count=counter.count(body),
                )
            )
    return chunks


def _units(section: ParsedSection, counter: TokenCounter, target: int) -> list[_Unit]:
    units: list[_Unit] = []
    stack: list[tuple[int, str]] = []
    offset = 0
    for block in section.blocks:
        start, end = offset, offset + len(block.text)
        offset = end + len(BLOCK_SEPARATOR)
        if block.heading_level is not None:
            while stack and stack[-1][0] >= block.heading_level:
                stack.pop()
            stack.append((block.heading_level, block.text))
            path = tuple(title for _, title in stack)
            units.append(_Unit(start, end, counter.count(block.text), True, path))
            continue
        path = tuple(title for _, title in stack)
        tokens = counter.count(block.text)
        if tokens <= target:
            units.append(_Unit(start, end, tokens, False, path))
            continue
        for s_start, s_end in sentence_spans(block.text) or [(0, len(block.text))]:
            sentence = block.text[s_start:s_end]
            s_tokens = counter.count(sentence)
            if s_tokens <= target:
                units.append(_Unit(start + s_start, start + s_end, s_tokens, False, path))
            else:
                units.extend(_word_windows(sentence, start + s_start, counter, target, path))
    return units


def _word_windows(
    text: str, base: int, counter: TokenCounter, target: int, path: tuple[str, ...]
) -> Iterator[_Unit]:
    words = list(_WORD.finditer(text))
    per_window = max(8, int(target * 0.7))
    for i in range(0, len(words), per_window):
        group = words[i : i + per_window]
        start, end = group[0].start(), group[-1].end()
        yield _Unit(base + start, base + end, counter.count(text[start:end]), False, path)


def _pack(units: list[_Unit], target: int, overlap: int) -> Iterator[tuple[int, int, str]]:
    i, n = 0, len(units)
    while i < n:
        j, total = i, 0
        while j < n and (j == i or total + units[j].tokens <= target):
            total += units[j].tokens
            j += 1
        while j - 1 > i and units[j - 1].is_heading:
            j -= 1
        window = units[i:j]
        body = next((u for u in window if not u.is_heading), window[-1])
        if any(not u.is_heading for u in window):
            yield window[0].start, window[-1].end, " > ".join(body.path)
        if j >= n:
            break
        back, carried = j, 0
        while (
            back - 1 > i
            and not units[back - 1].is_heading
            and carried + units[back - 1].tokens <= overlap
        ):
            back -= 1
            carried += units[back].tokens
        i = back


# Sentence windows ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Sentence:
    start: int
    end: int
    path: str


def _sentences(section: ParsedSection, counter: TokenCounter, limit: int) -> list[_Sentence]:
    found: list[_Sentence] = []
    stack: list[tuple[int, str]] = []
    offset = 0
    for block in section.blocks:
        start = offset
        offset = start + len(block.text) + len(BLOCK_SEPARATOR)
        if block.heading_level is not None:
            while stack and stack[-1][0] >= block.heading_level:
                stack.pop()
            stack.append((block.heading_level, block.text))
            continue
        path = " > ".join(title for _, title in stack)
        spans = sentence_spans(block.text) or [(0, len(block.text))]
        pending: int | None = None
        for index, (s_start, s_end) in enumerate(spans):
            pending = s_start if pending is None else pending
            last = index == len(spans) - 1
            if not last and len(block.text[pending:s_end].split()) < MIN_SENTENCE_WORDS:
                continue  # too short to retrieve on its own: joins the next sentence
            piece = block.text[pending:s_end]
            if counter.count(piece) <= limit:
                found.append(_Sentence(start + pending, start + s_end, path))
            else:
                found.extend(
                    _Sentence(unit.start, unit.end, path)
                    for unit in _word_windows(piece, start + pending, counter, limit, ())
                )
            pending = None
    return found


def _sentence_window(
    sections: Sequence[ParsedSection], counter: TokenCounter, options: ChunkingOptions
) -> list[ChunkDraft]:
    per = max(1, options.sentences_per_chunk)
    window = max(0, options.window_sentences)
    chunks: list[ChunkDraft] = []
    for ordinal, section in enumerate(sections):
        if not _has_body(section):
            continue
        text = section.text
        sentences = _sentences(section, counter, max(32, options.chunk_tokens))
        count = len(sentences)
        for first in range(0, count, per):
            last = min(count, first + per) - 1
            start, end = sentences[first].start, sentences[last].end
            context_start = sentences[max(0, first - window)].start
            context_end = sentences[min(count - 1, last + window)].end
            body = text[start:end]
            context = text[context_start:context_end]
            chunks.append(
                ChunkDraft(
                    section_ordinal=ordinal,
                    ordinal=len(chunks),
                    heading=sentences[first].path,
                    location=section.label,
                    text=body,
                    context=context if context != body else None,
                    char_start=start,
                    char_end=end,
                    token_count=counter.count(body),
                )
            )
    return chunks
