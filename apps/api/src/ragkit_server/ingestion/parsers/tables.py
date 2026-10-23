"""CSV tables: one section, one block per row.

Rows become "Column: value" records, so a retrieved row reads as a fact ("Plan: Growth;
Card fee: 2.7% + 30c") rather than a bare list of values. The first non-empty row names the
columns, and a short summary block lists them.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence

from ragkit_server.ingestion.types import (
    Block,
    ParsedDocument,
    ParsedSection,
    ParseError,
    ParseLimits,
)
from ragkit_server.models.enums import SectionKind


def rows_to_blocks(
    rows: Iterable[Sequence[str]], *, max_rows: int
) -> tuple[list[Block], int, bool]:
    """Header detection plus "Column: value" records. Returns blocks, data rows, truncated."""
    header: list[str] | None = None
    blocks: list[Block] = []
    data_rows = 0
    truncated = False
    for row in rows:
        cells = [cell.strip() for cell in row]
        if not any(cells):
            continue
        if header is None:
            header = [cell or f"Column {i + 1}" for i, cell in enumerate(cells)]
            continue
        if data_rows >= max_rows:
            truncated = True
            break
        pairs = [f"{name}: {value}" for name, value in zip(header, cells, strict=False) if value]
        blocks.append(Block("; ".join(pairs)))
        data_rows += 1
    if header is not None:
        summary = f"Columns: {', '.join(header)}. {data_rows} data row(s)."
        blocks.insert(0, Block(summary))
    return blocks, data_rows, truncated


def parse_csv(data: bytes, limits: ParseLimits) -> ParsedDocument:
    text = decode_text(data)
    sample = text[:16_384]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    blocks, _, truncated = rows_to_blocks(reader, max_rows=limits.max_rows_per_sheet)
    if not blocks:
        raise ParseError("This CSV file has no data.")
    warnings = (
        [f"Only the first {limits.max_rows_per_sheet:,} rows were indexed."] if truncated else []
    )
    return ParsedDocument(
        title=None, sections=[ParsedSection(SectionKind.TABLE, "Table", blocks)], warnings=warnings
    )


def decode_text(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")
