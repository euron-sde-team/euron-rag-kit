import pytest

from ragkit_server.core.errors import UnsupportedMediaTypeError
from ragkit_server.ingestion.sniff import (
    detect_kind,
    external_id_for,
    kind_for_response,
    slugify,
    title_from_filename,
)
from ragkit_server.models.enums import DocumentKind


def test_extension_and_bytes_must_agree() -> None:
    assert detect_kind("guide.md", b"# Title\n") is DocumentKind.MD
    assert detect_kind("sla.pdf", b"%PDF-1.7 ...") is DocumentKind.PDF
    assert detect_kind("policy.docx", b"PK\x03\x04rest") is DocumentKind.DOCX
    with pytest.raises(UnsupportedMediaTypeError) as mismatch:
        detect_kind("sla.pdf", b"MZ\x90\x00 an executable")
    assert mismatch.value.code == "content_mismatch"
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind("archive.zip", b"PK\x03\x04")
    with pytest.raises(UnsupportedMediaTypeError):
        detect_kind("notes.txt", b"binary\x00data")


def test_url_responses_use_the_content_type_and_trust_matching_suffixes() -> None:
    assert kind_for_response("text/html", "https://x.example/docs", b"<html>") is DocumentKind.HTML
    assert kind_for_response("text/plain", "https://x.example/README.md", b"# A") is DocumentKind.MD
    assert kind_for_response("text/plain", "https://x.example/notes", b"plain") is DocumentKind.TXT
    assert (
        kind_for_response("application/pdf", "https://x.example/a", b"%PDF-1.4") is DocumentKind.PDF
    )
    with pytest.raises(UnsupportedMediaTypeError):
        kind_for_response("image/png", "https://x.example/logo.png", b"\x89PNG")


def test_titles_slugs_and_external_ids() -> None:
    assert title_from_filename("webhooks_guide-v2.md") == "Webhooks guide v2"
    assert slugify("Webhooks Guide (v2)") == "webhooks-guide-v2"
    assert slugify("!!!") == "document"
    assert external_id_for("Service Level Agreement.pdf") == "service-level-agreement"
