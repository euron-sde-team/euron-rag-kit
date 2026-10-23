"""Plain text, Markdown and HTML.

Markdown and HTML are split into sections at their top-level headings, so a citation can
point at "Escalation" instead of "the whole file".
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ragkit_server.core.text import normalize
from ragkit_server.ingestion.parsers.common import blocks_from_text
from ragkit_server.ingestion.parsers.tables import decode_text
from ragkit_server.ingestion.types import (
    Block,
    ParsedDocument,
    ParsedSection,
    ParseError,
    ParseLimits,
)
from ragkit_server.models.enums import SectionKind

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_FENCE = re.compile(r"^(```|~~~)")
_MD_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_blocks(lines: list[str]) -> list[Block]:
    """Markdown tables become one "Column: value" record per row, like spreadsheets."""
    rows = [_cells(line) for line in lines if not _MD_TABLE_SEPARATOR.match(line.strip())]
    if len(rows) < 2:
        return [Block(" | ".join(rows[0]))] if rows else []
    header, *body = rows
    return [
        Block(
            "; ".join(f"{name}: {value}" for name, value in zip(header, row, strict=False) if value)
        )
        for row in body
    ]


def _sectioned(blocks: list[Block], default_label: str) -> list[ParsedSection]:
    """Start a new section at every level-1 or level-2 heading."""
    sections: list[ParsedSection] = []
    current = ParsedSection(SectionKind.SECTION, default_label)
    for block in blocks:
        if block.heading_level is not None and block.heading_level <= 2:
            if any(b.heading_level is None for b in current.blocks):
                sections.append(current)
                current = ParsedSection(SectionKind.SECTION, block.text[:300])
            else:
                current.label = block.text[:300]
        current.blocks.append(block)
    if current.blocks:
        sections.append(current)
    return sections


def parse_txt(data: bytes, limits: ParseLimits) -> ParsedDocument:
    blocks = blocks_from_text(decode_text(data))
    if not blocks:
        raise ParseError("This file has no text.")
    return ParsedDocument(title=None, sections=_sectioned(blocks, "Text"))


def parse_markdown(data: bytes, limits: ParseLimits) -> ParsedDocument:
    text = normalize(decode_text(data))
    blocks: list[Block] = []
    paragraph: list[str] = []
    in_code = False
    title: str | None = None

    def flush() -> None:
        if paragraph:
            blocks.append(Block(" ".join(paragraph) if not in_code else "\n".join(paragraph)))
            paragraph.clear()

    table: list[str] = []
    for line in [*text.split("\n"), ""]:
        if not in_code and line.lstrip().startswith("|"):
            flush()
            table.append(line)
            continue
        if table:
            blocks.extend(_table_blocks(table))
            table.clear()
        if _MD_FENCE.match(line):
            flush()
            in_code = not in_code
            continue
        if in_code:
            paragraph.append(line)
            continue
        heading = _MD_HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            if level == 1 and title is None:
                title = heading.group(2)
            blocks.append(Block(heading.group(2), heading_level=level))
        elif not line.strip():
            flush()
        elif re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            flush()
            paragraph.append("\u2022 " + re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line))
        else:
            paragraph.append(line.strip())
    flush()
    if not blocks:
        raise ParseError("This file has no text.")
    return ParsedDocument(title=title, sections=_sectioned(blocks, "Introduction"))


_HTML_BLOCKS = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "pre",
    "blockquote",
    "tr",
    "dt",
    "dd",
)


def parse_html(data: bytes, limits: ParseLimits) -> ParsedDocument:
    soup = BeautifulSoup(decode_text(data), "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "form"]):
        tag.decompose()
    title = normalize(soup.title.get_text()) if soup.title else None
    blocks: list[Block] = []
    for element in soup.find_all(_HTML_BLOCKS):
        if not isinstance(element, Tag) or element.find_parent(_HTML_BLOCKS):
            continue
        if element.name == "tr":
            cells = [normalize(c.get_text(" ")) for c in element.find_all(["td", "th"])]
            text = " | ".join(c for c in cells if c)
        else:
            text = normalize(element.get_text(" "))
        if not text:
            continue
        level = (
            int(element.name[1]) if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"} else None
        )
        prefix = "\u2022 " if element.name == "li" else ""
        blocks.append(Block(prefix + text, heading_level=level))
    if not blocks:
        raise ParseError("This page has no readable text.")
    return ParsedDocument(title=title or None, sections=_sectioned(blocks, title or "Page"))
