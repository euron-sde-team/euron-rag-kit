from ragkit_server.core.text import (
    content_terms,
    identifiers,
    normalize,
    normalize_for_match,
    numbers,
    split_sentences,
)


def test_normalize_collapses_spacing_and_blank_lines() -> None:
    assert normalize("A  b\t c\r\n\r\n\r\n\nNext   line") == "A b c\n\nNext line"


def test_sentences_respect_abbreviations_and_decimals() -> None:
    text = "Fees are 2.9% per charge, e.g. on cards. Refunds take 5 days. Done."
    assert split_sentences(text) == [
        "Fees are 2.9% per charge, e.g. on cards.",
        "Refunds take 5 days.",
        "Done.",
    ]


def test_content_terms_stem_and_drop_stopwords() -> None:
    assert content_terms("The webhooks are retrying events") == ["webhook", "retry", "event"]


def test_possessives_fold_into_their_noun() -> None:
    assert content_terms("the customer's statement") == ["customer", "statement"]
    assert content_terms("the customer\N{RIGHT SINGLE QUOTATION MARK}s bank") == [
        "customer",
        "bank",
    ]


def test_numbers_are_normalised() -> None:
    text = "Fees are 2.90% + $0.30, capped at $1,200.50; respond within 15 minutes."
    assert numbers(text) == ["2.9", "0.3", "1200.5", "15"]


def test_numbers_skip_parts_of_identifiers_and_dates() -> None:
    assert numbers("Error ACME-4011 on 2026-12-31") == ["2026"]


def test_identifiers_find_code_like_tokens() -> None:
    text = (
        "Send the Idempotency-Key header; ACME-4011 means max_retries=3 hit, see paymentIntent v2."
    )
    assert identifiers(text) == [
        "idempotency-key",
        "acme-4011",
        "max_retries",
        "paymentintent",
        "v2",
    ]


def test_plain_words_and_numbers_are_not_identifiers() -> None:
    assert identifiers("An e-mail about TLS 1.2 and Webhooks.") == []


def test_normalize_for_match_ignores_case_and_punctuation() -> None:
    assert normalize_for_match("SEV1  incidents: page on-call!") == "sev1 incidents page on call"
