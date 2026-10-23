from __future__ import annotations

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ragkit_server.ingestion.parsers.common import blocks_from_layout
from ragkit_server.ingestion.types import ParsedDocument, ParsedSection, ParseError, ParseLimits
from ragkit_server.models.enums import SectionKind

# pypdf logs every malformed object it recovers from; those are not our errors.
logging.getLogger("pypdf").setLevel(logging.ERROR)


def parse_pdf(data: bytes, limits: ParseLimits) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError("This PDF is password-protected. Remove the password and retry.")
        page_count = len(reader.pages)
    except PdfReadError as exc:
        raise ParseError("This PDF is damaged or not a PDF.") from exc

    if page_count > limits.max_pages:
        raise ParseError(f"This PDF has {page_count} pages; the limit is {limits.max_pages}.")

    title = None
    try:
        title = (reader.metadata.title or "").strip() if reader.metadata else None
    except PdfReadError:
        title = None

    sections: list[ParsedSection] = []
    empty: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            # Layout mode keeps each table row on one line, so tables survive extraction.
            raw = page.extract_text(extraction_mode="layout") or ""
            # Many generators draw list bullets with a glyph that extracts as DEL.
            raw = raw.replace("\x7f", "\u2022")
        except Exception:
            raw = ""
        blocks = blocks_from_layout(raw)
        if not blocks:
            empty.append(number)
            continue
        sections.append(ParsedSection(SectionKind.PAGE, f"Page {number}", blocks))

    if not sections:
        raise ParseError(
            "No readable text was found. Scanned PDFs need OCR before they can be searched."
        )
    warnings = []
    if empty:
        listed = ", ".join(str(n) for n in empty[:10]) + ("..." if len(empty) > 10 else "")
        warnings.append(
            f"{len(empty)} page(s) had no extractable text and were skipped "
            f"(scanned images need OCR): {listed}"
        )
    return ParsedDocument(title=title or None, sections=sections, warnings=warnings)
