import pytest

from ragkit_server.ingestion.parsers.registry import parse
from ragkit_server.ingestion.types import ParseError, ParseLimits
from ragkit_server.models.enums import DocumentKind, SectionKind

LIMITS = ParseLimits()


def test_markdown_splits_sections_at_headings_and_keeps_levels() -> None:
    doc = parse(
        DocumentKind.MD,
        b"# Webhooks\n\nIntro text here.\n\n## Retries\n\n- one\n- two\n\n## Signatures\n\nUse HMAC.\n",
        LIMITS,
    )
    assert doc.title == "Webhooks"
    assert [s.label for s in doc.sections] == ["Webhooks", "Retries", "Signatures"]
    retries = doc.sections[1]
    assert retries.blocks[0].heading_level == 2
    assert retries.blocks[1].text == "\N{BULLET} one"


def test_markdown_tables_become_records() -> None:
    doc = parse(DocumentKind.MD, b"| Plan | Fee |\n|---|---|\n| Starter | 2.9% |\n", LIMITS)
    assert doc.sections[0].blocks[0].text == "Plan: Starter; Fee: 2.9%"


def test_html_drops_navigation_and_scripts() -> None:
    html = (
        b"<html><head><title>Payouts</title><script>var x=1</script></head><body>"
        b"<nav>Home | Docs</nav><h1>Payouts</h1><p>Payouts arrive in two business days.</p>"
        b"<ul><li>Daily</li><li>Weekly</li></ul></body></html>"
    )
    doc = parse(DocumentKind.HTML, html, LIMITS)
    text = "\n".join(b.text for s in doc.sections for b in s.blocks)
    assert doc.title == "Payouts"
    assert "Payouts arrive in two business days." in text
    assert "var x" not in text
    assert "Home | Docs" not in text
    assert "\N{BULLET} Daily" in text


def test_plain_text_and_csv() -> None:
    txt = parse(DocumentKind.TXT, b"Release 2026.10\n\nAdded refunds API.\n", LIMITS)
    assert txt.sections[0].blocks[-1].text == "Added refunds API."
    csv = parse(DocumentKind.CSV, b"plan,fee\nStarter,2.9%\nGrowth,2.7%\n", LIMITS)
    assert csv.sections[0].kind is SectionKind.TABLE
    assert [b.text for b in csv.sections[0].blocks][1:] == [
        "plan: Starter; fee: 2.9%",
        "plan: Growth; fee: 2.7%",
    ]


def test_empty_and_broken_files_raise_parse_errors() -> None:
    with pytest.raises(ParseError):
        parse(DocumentKind.TXT, b"   \n ", LIMITS)
    with pytest.raises(ParseError):
        parse(DocumentKind.PDF, b"%PDF-1.4 not really a pdf", LIMITS)
    with pytest.raises(ParseError):
        parse(DocumentKind.DOCX, b"PK\x03\x04 not a zip", LIMITS)
