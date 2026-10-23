import itertools

import pytest

from ragkit_server.ai.tokens import TokenCounter

TEXT = " ".join(
    f"word{i} is part of a long sentence about payments and refunds." for i in range(40)
)


@pytest.mark.parametrize("mode", ["tiktoken", "heuristic"])
def test_windows_cover_the_text_without_gaps(mode: str) -> None:
    counter = TokenCounter(mode)
    spans = counter.windows(TEXT, 50, 0)
    assert spans[0][0] == 0
    assert spans[-1][1] == len(TEXT)
    for (_, end), (start, _) in itertools.pairwise(spans):
        assert TEXT[end:start].strip() == ""  # consecutive windows touch at a word boundary


@pytest.mark.parametrize("mode", ["tiktoken", "heuristic"])
def test_windows_respect_size_and_overlap(mode: str) -> None:
    counter = TokenCounter(mode)
    spans = counter.windows(TEXT, 60, 15)
    assert len(spans) > 3
    for start, end in spans[:-1]:
        assert 55 <= counter.count(TEXT[start:end]) <= 66
    first, second = spans[0], spans[1]
    assert second[0] < first[1]  # overlap


def test_windows_never_split_a_word() -> None:
    counter = TokenCounter()
    for start, end in counter.windows(TEXT, 17, 5):
        assert start == 0 or TEXT[start - 1] == " "
        assert end == len(TEXT) or TEXT[end] == " "


def test_empty_text_has_no_windows_and_counts_zero() -> None:
    counter = TokenCounter()
    assert counter.windows("   ", 10, 2) == []
    assert counter.count("") == 0
    assert counter.truncate("one two three four", 2) in ("one two", " one two")
