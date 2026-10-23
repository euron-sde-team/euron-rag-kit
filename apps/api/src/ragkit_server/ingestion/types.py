"""What every parser returns: ordered sections made of text blocks."""

from __future__ import annotations

from dataclasses import dataclass, field

from ragkit_server.models.enums import SectionKind


class ParseError(Exception):
    """A problem with the file itself, safe to show to the person who uploaded it."""


@dataclass(slots=True)
class Block:
    text: str
    # 1 for a top-level heading, 2 for a subheading, and so on; None for body text.
    heading_level: int | None = None


@dataclass(slots=True)
class ParsedSection:
    kind: SectionKind
    label: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def text(self) -> str:
        return BLOCK_SEPARATOR.join(block.text for block in self.blocks)


@dataclass(slots=True)
class ParsedDocument:
    title: str | None
    sections: list[ParsedSection]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ParseLimits:
    max_pages: int = 2000
    max_rows_per_sheet: int = 50_000
    max_uncompressed_bytes: int = 400 * 1024 * 1024


BLOCK_SEPARATOR = "\n\n"
