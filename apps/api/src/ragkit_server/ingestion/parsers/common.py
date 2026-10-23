"""Helpers for turning flat extracted text into paragraphs and headings."""

from __future__ import annotations

import re

from ragkit_server.core.text import normalize
from ragkit_server.ingestion.types import Block

_BULLET = re.compile(r"^([\u2022\u25cf\u25aa\u2013*-]|\d{1,3}[.)]|[a-z][.)])\s+")
_SECTION_NUMBER = re.compile(r"^(\d{1,2}(\.\d{1,2})*\.?|[IVX]{1,4}\.)\s+(?=[A-Z])")
_SENTENCE_END = (".", "!", "?", ":", ";", ",")
_PARAGRAPH_END = (".", "!", "?", ":")
# A heading line ending in one of these words continues on the next line.
_CONNECTORS = frozenset({"and", "of", "the", "for", "to", "in", "with", "on", "at", "a", "an", "&"})


def looks_like_heading(line: str) -> bool:
    """A short, capitalised line without closing punctuation.

    Callers only ask once the previous paragraph has ended, which is what separates a
    sentence-case heading ("Travel and expenses") from the last line of a paragraph.
    """
    numbered = _SECTION_NUMBER.match(line)
    if numbered:
        line = line[numbered.end() :]
    words = line.split()
    if not 1 <= len(words) <= 10 or len(line) > 80 or line.endswith((*_SENTENCE_END, "-")):
        return False
    if not numbered and _BULLET.match(line):
        return False
    return line[0].isalpha() and line[0].isupper()


def blocks_from_text(raw: str, *, detect_headings: bool = True) -> list[Block]:
    """Rebuild paragraphs from line-broken text (PDF pages, plain text files).

    Lines are joined into a paragraph until a blank line, a bullet, or a heading-like line.
    Words hyphenated across a line break are rejoined.
    """
    blocks: list[Block] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append(Block(" ".join(current)))
            current.clear()

    lines = normalize(raw).split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line:
            flush()
            continue
        # PDF text has no blank line before a heading, so a heading may follow a paragraph
        # directly; it can only start once that paragraph has ended.
        paragraph_done = not current or current[-1].endswith(_PARAGRAPH_END)
        numbered = bool(_SECTION_NUMBER.match(line))
        if (
            detect_headings
            and paragraph_done
            and index < len(lines)
            and (numbered or not _BULLET.match(line))
        ):
            candidate, consumed = line, index
            while (
                candidate.split()[-1].lower() in _CONNECTORS
                and consumed < len(lines)
                and lines[consumed]
                and len(candidate) + len(lines[consumed]) < 120
            ):
                candidate = f"{candidate} {lines[consumed]}"
                consumed += 1
            if looks_like_heading(candidate):
                flush()
                blocks.append(Block(candidate, heading_level=2))
                index = consumed
                continue
        if _BULLET.match(line):
            flush()
        if current and current[-1].endswith("-") and line[:1].islower():
            current[-1] = current[-1][:-1] + line
        else:
            current.append(line)
    flush()
    return blocks


_COLUMN_GAP = re.compile(r"\s{2,}")


def _row_cells(line: str) -> list[str]:
    return [normalize(cell) for cell in _COLUMN_GAP.split(line.strip()) if cell.strip()]


def blocks_from_layout(raw: str) -> list[Block]:
    """Like `blocks_from_text`, for layout-preserving PDF text, with tables recovered.

    In layout mode a table row is one line whose cells are separated by runs of spaces.
    Two or more consecutive lines with at least three cells are read as a table: the first
    row names the columns and every other row becomes a "Column: value" record.
    """
    blocks: list[Block] = []
    text_lines: list[str] = []
    table: list[list[str]] = []

    def flush_text() -> None:
        if text_lines:
            blocks.extend(blocks_from_text("\n".join(text_lines)))
            text_lines.clear()

    def flush_table() -> None:
        if len(table) >= 2:
            header, *rows = table
            for row in rows:
                pairs = [
                    f"{name}: {value}" for name, value in zip(header, row, strict=False) if value
                ]
                blocks.append(Block("; ".join(pairs)))
        else:
            text_lines.extend(" ".join(row) for row in table)
        table.clear()

    for line in raw.split("\n"):
        if not line.strip():
            if not table:  # layout mode puts blank lines between table rows
                text_lines.append(line)
            continue
        cells = _row_cells(line)
        if len(cells) >= 3:
            if not table:
                flush_text()
            table.append(cells)
            continue
        if table:
            flush_table()
        text_lines.append(line)
    flush_table()
    flush_text()
    return blocks
