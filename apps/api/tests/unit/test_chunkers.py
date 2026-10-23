import pytest

from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.ingestion.chunkers import ChunkingOptions, chunk_sections
from ragkit_server.ingestion.types import Block, ParsedSection
from ragkit_server.models.enums import SectionKind

COUNTER = TokenCounter()
SENTENCE = "Refunds are issued to the original payment method within five business days."


def section(label: str, *blocks: Block) -> ParsedSection:
    return ParsedSection(SectionKind.SECTION, label, list(blocks))


GUIDE = [
    section(
        "Refunds",
        Block("Refunds", heading_level=1),
        Block(" ".join([SENTENCE] * 6)),
        Block("Partial refunds", heading_level=2),
        Block("You can refund part of a charge. The rest stays captured. Fees are not returned."),
    ),
    section("Empty", Block("Only a heading", heading_level=1)),
    section(
        "Disputes",
        Block("Disputes", heading_level=1),
        Block("Respond to a dispute within 7 days. Upload evidence such as receipts."),
    ),
]


def test_recursive_chunks_stay_inside_sections_and_carry_heading_paths() -> None:
    chunks = chunk_sections(GUIDE, COUNTER, ChunkingOptions("recursive", 40, 10))
    assert {c.section_ordinal for c in chunks} == {0, 2}  # the empty section is skipped
    for chunk in chunks:
        assert GUIDE[chunk.section_ordinal].text[chunk.char_start : chunk.char_end] == chunk.text
        assert chunk.token_count <= 60
        assert chunk.context is None
    partial = next(c for c in chunks if "part of a charge" in c.text)
    assert partial.heading == "Refunds > Partial refunds"
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_recursive_never_ends_a_chunk_on_a_heading() -> None:
    chunks = chunk_sections(GUIDE, COUNTER, ChunkingOptions("recursive", 40, 0))
    assert not any(c.text.endswith("Partial refunds") for c in chunks)


def test_recursive_overlap_repeats_whole_units() -> None:
    long_block = Block(" ".join(f"Sentence number {i} explains a payout rule." for i in range(30)))
    chunks = chunk_sections(
        [section("Payouts", long_block)], COUNTER, ChunkingOptions("recursive", 50, 20)
    )
    assert len(chunks) > 3
    assert chunks[1].char_start < chunks[0].char_end


def test_fixed_windows_ignore_structure_and_cover_the_document() -> None:
    chunks = chunk_sections(GUIDE, COUNTER, ChunkingOptions("fixed", 30, 0))
    joined = "\n\n".join(s.text for s in (GUIDE[0], GUIDE[2]))
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(joined)
    assert all(c.heading == "" for c in chunks)
    assert chunks[-1].location == "Disputes"
    for chunk in chunks:
        assert joined[chunk.char_start : chunk.char_end] == chunk.text


def test_sentence_windows_index_small_units_with_wider_context() -> None:
    options = ChunkingOptions("sentence_window", sentences_per_chunk=1, window_sentences=1)
    chunks = chunk_sections(GUIDE, COUNTER, options)
    dispute = next(c for c in chunks if c.text.startswith("Respond to a dispute"))
    assert dispute.text == "Respond to a dispute within 7 days."
    assert dispute.context is not None
    assert "Upload evidence such as receipts." in dispute.context
    assert dispute.heading == "Disputes"
    rest = next(c for c in chunks if c.text.startswith("The rest stays captured"))
    assert rest.context == (
        "You can refund part of a charge. The rest stays captured. Fees are not returned."
    )


def test_short_sentences_merge_with_the_next() -> None:
    block = Block("Yes. It works. Refunds are always issued to the original card on file.")
    chunks = chunk_sections(
        [section("FAQ", block)], COUNTER, ChunkingOptions("sentence_window", sentences_per_chunk=1)
    )
    assert chunks[0].text.startswith("Yes. It works. Refunds")


@pytest.mark.parametrize("strategy", ["fixed", "recursive", "sentence_window"])
def test_every_strategy_handles_an_empty_document(strategy: str) -> None:
    options = ChunkingOptions(strategy)  # type: ignore[arg-type]
    assert (
        chunk_sections([section("Empty", Block("Title", heading_level=1))], COUNTER, options) == []
    )
