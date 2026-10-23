"""Decide what a source is from its name, its Content-Type *and* its bytes.

For uploads the extension picks the parser and the magic bytes must agree, so a renamed
executable or a mislabeled file is refused before any parser sees it. For URL sources the
response's Content-Type picks the parser, with the same byte check.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath

from ragkit_server.core.errors import UnsupportedMediaTypeError
from ragkit_server.models.enums import DocumentKind

EXTENSIONS: dict[str, DocumentKind] = {
    ".pdf": DocumentKind.PDF,
    ".docx": DocumentKind.DOCX,
    ".md": DocumentKind.MD,
    ".markdown": DocumentKind.MD,
    ".html": DocumentKind.HTML,
    ".htm": DocumentKind.HTML,
    ".txt": DocumentKind.TXT,
    ".csv": DocumentKind.CSV,
}

MIME_TYPES: dict[DocumentKind, str] = {
    DocumentKind.PDF: "application/pdf",
    DocumentKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    DocumentKind.MD: "text/markdown",
    DocumentKind.HTML: "text/html",
    DocumentKind.TXT: "text/plain",
    DocumentKind.CSV: "text/csv",
}

FILE_EXTENSIONS: dict[DocumentKind, str] = {
    DocumentKind.PDF: ".pdf",
    DocumentKind.DOCX: ".docx",
    DocumentKind.MD: ".md",
    DocumentKind.HTML: ".html",
    DocumentKind.TXT: ".txt",
    DocumentKind.CSV: ".csv",
}

CONTENT_TYPES: dict[str, DocumentKind] = {
    "application/pdf": DocumentKind.PDF,
    "text/html": DocumentKind.HTML,
    "application/xhtml+xml": DocumentKind.HTML,
    "text/markdown": DocumentKind.MD,
    "text/x-markdown": DocumentKind.MD,
    "text/plain": DocumentKind.TXT,
    "text/csv": DocumentKind.CSV,
}

_TEXT = {DocumentKind.MD, DocumentKind.HTML, DocumentKind.TXT, DocumentKind.CSV}
SUPPORTED_LABEL = "PDF, Word (.docx), Markdown, HTML, text or CSV"


def detect_kind(filename: str, head: bytes) -> DocumentKind:
    suffix = PurePath(filename).suffix.lower()
    kind = EXTENSIONS.get(suffix)
    if kind is None:
        raise UnsupportedMediaTypeError(
            f"{suffix or 'Files without an extension'} is not supported. Upload {SUPPORTED_LABEL}."
        )
    if not content_matches(kind, head):
        raise UnsupportedMediaTypeError(
            f"The file's content does not match its {suffix} extension.",
            code="content_mismatch",
        )
    return kind


def kind_for_response(content_type: str, url: str, head: bytes) -> DocumentKind:
    """The parser for a fetched URL: the Content-Type decides, the URL's suffix breaks ties."""
    kind = CONTENT_TYPES.get(content_type)
    if kind is None or kind is DocumentKind.TXT:
        # Many servers label Markdown and CSV as text/plain; trust a matching suffix then.
        by_suffix = EXTENSIONS.get(PurePath(url.split("?", 1)[0]).suffix.lower())
        if by_suffix in _TEXT:
            kind = by_suffix
    if kind is None:
        raise UnsupportedMediaTypeError(
            f"The URL returned {content_type or 'an unknown type'}; RAGKit loads "
            f"{SUPPORTED_LABEL} pages."
        )
    if not content_matches(kind, head):
        raise UnsupportedMediaTypeError(
            "The page's content does not match its type.", code="content_mismatch"
        )
    return kind


def content_matches(kind: DocumentKind, head: bytes) -> bool:
    if kind is DocumentKind.PDF:
        return b"%PDF-" in head[:1024]
    if kind is DocumentKind.DOCX:
        return head[:4] == b"PK\x03\x04"
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return True  # UTF-16 text legitimately contains NUL bytes
    return b"\x00" not in head[:8192]


def title_from_filename(filename: str) -> str:
    stem = PurePath(filename).stem.replace("_", " ").replace("-", " ").strip()
    stem = re.sub(r"\s+", " ", stem)
    return stem[:1].upper() + stem[1:] if stem else "Untitled document"


def slugify(value: str, *, limit: int = 120, fallback: str = "document") -> str:
    """A lowercase, hyphenated ASCII identifier: "Webhooks Guide (v2)" is webhooks-guide-v2."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:limit].strip("-") or fallback


def external_id_for(filename_or_title: str) -> str:
    """The default external id of a source: its file stem (or title), slugified."""
    return slugify(PurePath(filename_or_title).stem or filename_or_title)
