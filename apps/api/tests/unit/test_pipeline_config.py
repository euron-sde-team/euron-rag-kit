import pytest
from pydantic import ValidationError

from ragkit_server.ai.embeddings import REGISTRY
from ragkit_server.schemas.pipeline import (
    AnswerOverrides,
    PipelineConfig,
    RetrievalOverrides,
    apply_answer,
    apply_retrieval,
    fingerprint,
    index_settings,
)
from ragkit_server.services.evaluation import default_label

BGE = REGISTRY["bge-small-en-v1.5"]


def print_of(config: dict) -> str:  # type: ignore[type-arg]
    return fingerprint(index_settings(PipelineConfig.model_validate(config), BGE))


def test_an_empty_configuration_is_valid_with_documented_defaults() -> None:
    config = PipelineConfig()
    assert config.chunking.strategy == "recursive"
    assert config.retrieval.mode == "hybrid"
    assert config.answer.answerer == "extractive"


def test_retrieval_and_answer_changes_keep_the_index() -> None:
    base = print_of({})
    assert print_of({"retrieval": {"mode": "vector", "rerank": "cross-encoder"}}) == base
    assert print_of({"answer": {"max_sources": 3}}) == base


def test_index_settings_changes_build_a_new_index() -> None:
    base = print_of({})
    assert print_of({"chunking": {"chunk_tokens": 200}}) != base
    assert print_of({"cleaning": {"strip_boilerplate": True}}) != base
    assert print_of({"embedding": {"contextual": False}}) != base


def test_unused_chunking_knobs_never_split_an_index() -> None:
    windows = {"chunking": {"strategy": "sentence_window"}}
    assert print_of(windows) == print_of(
        {"chunking": {"strategy": "sentence_window", "overlap_tokens": 10}}
    )
    assert print_of({}) == print_of({"chunking": {"window_sentences": 5}})


def test_invalid_configurations_are_refused() -> None:
    for bad in (
        {"chunking": {"chunk_tokens": 100, "overlap_tokens": 60}},
        {"retrieval": {"top_k": 20, "candidates": 10}},
        {"chunkng": {}},
        {"retrieval": {"mode": "semantic"}},
    ):
        with pytest.raises(ValidationError):
            PipelineConfig.model_validate(bad)


def test_overrides_merge_and_keep_enough_candidates() -> None:
    base = PipelineConfig().retrieval
    merged = apply_retrieval(base, RetrievalOverrides(top_k=50, rerank="lexical"))
    assert (merged.top_k, merged.candidates, merged.rerank, merged.mode) == (
        50,
        50,
        "lexical",
        "hybrid",
    )
    assert apply_retrieval(base, None) is base
    answer = apply_answer(PipelineConfig().answer, AnswerOverrides(max_sources=2))
    assert answer.max_sources == 2


def test_run_labels_say_what_was_measured() -> None:
    config = PipelineConfig.model_validate(
        {
            "chunking": {"strategy": "sentence_window"},
            "retrieval": {"rerank": "cross-encoder", "fusion": "weighted"},
        }
    )
    assert default_label(3, config) == "v3 sentence window, hybrid (weighted) + cross-encoder"
    assert (
        default_label(1, PipelineConfig.model_validate({"retrieval": {"mode": "vector"}}))
        == "v1 recursive, vector"
    )
