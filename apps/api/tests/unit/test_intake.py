import pytest

from ragkit_server.core.errors import UnprocessableError
from ragkit_server.retrieval.keyword import keyword_query
from ragkit_server.services.documents import clean_filename, url_external_id, validate_metadata


def test_keyword_queries_or_the_meaningful_words() -> None:
    assert keyword_query("How do I verify the ACME-4011 webhook signature?") == (
        "verify | acme | 4011 | webhook | signature"
    )
    assert keyword_query("what is it?") is None


def test_metadata_keys_must_be_filterable_and_small() -> None:
    assert validate_metadata({"section": "guides", "year": 2026}) == {
        "section": "guides",
        "year": 2026,
    }
    with pytest.raises(UnprocessableError) as bad_key:
        validate_metadata({"bad key": 1})
    assert bad_key.value.code == "invalid_metadata"
    with pytest.raises(UnprocessableError):
        validate_metadata({"blob": "x" * 9000})


def test_filenames_lose_paths_and_control_characters() -> None:
    assert clean_filename("../../etc/passwd") == "passwd"
    assert clean_filename("C:\\docs\\guide\x07.md") == "guide.md"
    assert clean_filename("") == "upload"


def test_url_sources_get_readable_external_ids() -> None:
    assert (
        url_external_id("https://docs.example.com/guides/webhooks?x=1")
        == "docs-example-com-guides-webhooks"
    )
