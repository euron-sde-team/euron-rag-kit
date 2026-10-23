"""Cleaning rules applied to parsed blocks before chunking.

Each rule is a switch in the pipeline configuration, so its effect on retrieval can be
measured: create a version with the rule on, evaluate both, compare. Rules run in a fixed
order (unicode, whitespace, boilerplate, duplicates, emails, short blocks) and report what
they removed, which the dashboard shows next to the chunking preview.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from ragkit_server.ingestion.types import Block, ParsedSection

_INVISIBLE = dict.fromkeys(
    map(
        ord,
        "\N{SOFT HYPHEN}\N{ZERO WIDTH SPACE}\N{ZERO WIDTH NON-JOINER}"
        "\N{ZERO WIDTH JOINER}\N{ZERO WIDTH NO-BREAK SPACE}",
    )
)
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DIGITS = re.compile(r"\d+")
BOILERPLATE_MAX_CHARS = 120


@dataclass(frozen=True, slots=True)
class CleaningOptions:
    normalize_unicode: bool = True
    collapse_whitespace: bool = True
    strip_boilerplate: bool = False
    drop_duplicate_blocks: bool = False
    redact_emails: bool = False
    min_block_chars: int = 0


@dataclass(slots=True)
class CleaningReport:
    boilerplate_blocks: int = 0
    duplicate_blocks: int = 0
    short_blocks: int = 0
    emails_redacted: int = 0
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "boilerplate_blocks": self.boilerplate_blocks,
            "duplicate_blocks": self.duplicate_blocks,
            "short_blocks": self.short_blocks,
            "emails_redacted": self.emails_redacted,
            "examples": self.examples[:5],
        }


def _normalize_unicode(text: str) -> str:
    # NFKC folds the ligatures PDF extraction produces ("fi" as one glyph) and odd spaces.
    return unicodedata.normalize("NFKC", text).translate(_INVISIBLE)


def _collapse(text: str) -> str:
    lines = [_HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _signature(text: str) -> str:
    """What repeated headers and footers share: "Page 3 of 9" and "Page 4 of 9" match."""
    return _DIGITS.sub("#", " ".join(text.lower().split()))


def _edges(section: ParsedSection) -> list[Block]:
    """Where headers and footers live: the first and last two blocks of a section."""
    blocks = section.blocks
    return blocks if len(blocks) <= 4 else [*blocks[:2], *blocks[-2:]]


def _boilerplate(sections: Sequence[ParsedSection]) -> set[str]:
    if len(sections) < 3:
        return set()
    seen: Counter[str] = Counter()
    for section in sections:
        signatures = {
            _signature(block.text)
            for block in _edges(section)
            if len(block.text) <= BOILERPLATE_MAX_CHARS
        }
        seen.update(signatures)
    threshold = max(3, math.ceil(len(sections) / 2))
    return {signature for signature, count in seen.items() if count >= threshold}


def clean_sections(
    sections: Sequence[ParsedSection], options: CleaningOptions
) -> tuple[list[ParsedSection], CleaningReport]:
    report = CleaningReport()
    staged: list[ParsedSection] = []
    for section in sections:
        blocks: list[Block] = []
        for block in section.blocks:
            text = block.text
            if options.normalize_unicode:
                text = _normalize_unicode(text)
            if options.collapse_whitespace:
                text = _collapse(text)
            if text:
                blocks.append(Block(text, heading_level=block.heading_level))
        staged.append(ParsedSection(section.kind, section.label, blocks))

    repeated = _boilerplate(staged) if options.strip_boilerplate else set()
    seen_bodies: set[str] = set()
    cleaned: list[ParsedSection] = []
    for section in staged:
        edges = {id(block) for block in _edges(section)}
        blocks = []
        for block in section.blocks:
            text = block.text
            if (
                repeated
                and id(block) in edges
                and len(text) <= BOILERPLATE_MAX_CHARS
                and _signature(text) in repeated
            ):
                report.boilerplate_blocks += 1
                if len(report.examples) < 5 and text not in report.examples:
                    report.examples.append(text)
                continue
            is_heading = block.heading_level is not None
            if options.drop_duplicate_blocks and not is_heading:
                key = " ".join(text.lower().split())
                if key in seen_bodies:
                    report.duplicate_blocks += 1
                    continue
                seen_bodies.add(key)
            if options.redact_emails:
                text, count = _EMAIL.subn("[email]", text)
                report.emails_redacted += count
            if not is_heading and len(text) < options.min_block_chars:
                report.short_blocks += 1
                continue
            blocks.append(Block(text, heading_level=block.heading_level))
        # Kept even when emptied, so section ordinals still match the parsed document;
        # the chunkers skip sections without body text.
        cleaned.append(ParsedSection(section.kind, section.label, blocks))
    return cleaned, report
