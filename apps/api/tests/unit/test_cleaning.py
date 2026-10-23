from ragkit_server.ingestion.cleaning import CleaningOptions, clean_sections
from ragkit_server.ingestion.types import Block, ParsedSection
from ragkit_server.models.enums import SectionKind


def page(number: int, *body: str) -> ParsedSection:
    blocks = [Block(f"Acme Payments: confidential, page {number} of 9"), *(Block(t) for t in body)]
    return ParsedSection(SectionKind.PAGE, f"Page {number}", blocks)


def texts(sections: list[ParsedSection]) -> list[str]:
    return [block.text for section in sections for block in section.blocks]


def test_unicode_and_whitespace_are_normalised() -> None:
    raw = ParsedSection(
        SectionKind.SECTION,
        "Intro",
        [
            Block(
                "The \N{LATIN SMALL LIGATURE FI}rst  re\N{SOFT HYPHEN}fund\tis free\N{ZERO WIDTH SPACE}."
            )
        ],
    )
    cleaned, _ = clean_sections([raw], CleaningOptions())
    assert texts(cleaned) == ["The first refund is free."]


BODIES = (
    "Payouts arrive in two business days.",
    "Refunds return to the original card.",
    "Disputes need evidence within seven days.",
    "Webhooks retry for up to three days.",
)


def test_repeated_headers_and_footers_are_stripped() -> None:
    pages = [page(n, body) for n, body in enumerate(BODIES, start=1)]
    cleaned, report = clean_sections(pages, CleaningOptions(strip_boilerplate=True))
    assert report.boilerplate_blocks == 4
    assert texts(cleaned) == list(BODIES)
    assert len(cleaned) == 4  # ordinals stay aligned with the parsed document


def test_body_text_in_the_middle_of_a_page_is_never_boilerplate() -> None:
    middle = "Totals are reported per page."
    pages = [
        page(n, "First paragraph.", "Second paragraph.", middle, "Fourth one.", "Fifth one.")
        for n in range(1, 5)
    ]
    cleaned, _ = clean_sections(pages, CleaningOptions(strip_boilerplate=True))
    assert texts(cleaned).count(middle) == 4


def test_boilerplate_needs_three_repeats() -> None:
    pages = [page(n, "Body.") for n in range(1, 3)]
    _, report = clean_sections(pages, CleaningOptions(strip_boilerplate=True))
    assert report.boilerplate_blocks == 0


def test_duplicates_emails_and_short_blocks() -> None:
    section = ParsedSection(
        SectionKind.SECTION,
        "Contact",
        [
            Block("Contact", heading_level=2),
            Block("Write to support@acme-payments.example for help."),
            Block("Write to support@acme-payments.example for help."),
            Block("OK"),
        ],
    )
    options = CleaningOptions(drop_duplicate_blocks=True, redact_emails=True, min_block_chars=5)
    cleaned, report = clean_sections([section], options)
    assert texts(cleaned) == ["Contact", "Write to [email] for help."]
    assert (report.duplicate_blocks, report.emails_redacted, report.short_blocks) == (1, 1, 1)
