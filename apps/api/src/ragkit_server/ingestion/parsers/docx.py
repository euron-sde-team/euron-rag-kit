from __future__ import annotations

import io

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from ragkit_server.core.text import normalize
from ragkit_server.ingestion.archive import check_ooxml
from ragkit_server.ingestion.types import (
    Block,
    ParsedDocument,
    ParsedSection,
    ParseError,
    ParseLimits,
)
from ragkit_server.models.enums import SectionKind


def _heading_level(paragraph: Paragraph) -> int | None:
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    if style == "Title":
        return 1
    if style.startswith("Heading"):
        suffix = style.removeprefix("Heading").strip()
        return int(suffix) if suffix.isdigit() else 1
    return None


def _table_blocks(table: Table) -> list[Block]:
    rows = [[normalize(cell.text) for cell in row.cells] for row in table.rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    header, *body = rows
    if not body:
        return [Block(" | ".join(header))]
    lines = []
    for row in body:
        pairs = [f"{h}: {v}" for h, v in zip(header, row, strict=False) if v and h]
        lines.append("; ".join(pairs) if pairs else " | ".join(row))
    return [Block(line) for line in lines]


def parse_docx(data: bytes, limits: ParseLimits) -> ParsedDocument:
    check_ooxml(
        data,
        required_prefix="word/",
        label="Word document",
        max_uncompressed=limits.max_uncompressed_bytes,
    )
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ParseError("This Word document could not be read.") from exc

    title = (document.core_properties.title or "").strip() or None
    sections: list[ParsedSection] = []
    current = ParsedSection(SectionKind.SECTION, "Introduction")

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = normalize(item.text)
            if not text:
                continue
            level = _heading_level(item)
            if level == 1 and title is None:
                title = text
            if level is not None and level <= 1 and current.blocks:
                sections.append(current)
                current = ParsedSection(SectionKind.SECTION, text)
            elif level is not None and level <= 1:
                current.label = text
            style = (item.style.name if item.style is not None else "") or ""
            if level is None and style.startswith("List"):
                text = f"\u2022 {text}"
            current.blocks.append(Block(text, heading_level=level))
        elif isinstance(item, Table):
            current.blocks.extend(_table_blocks(item))
    if current.blocks:
        sections.append(current)

    if not sections:
        raise ParseError("This Word document has no text.")
    return ParsedDocument(title=title, sections=sections)
