import httpx
import pytest
import respx

from ragkit_server.ai.answerers import Answerers, build_chat_client
from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.core.config import Settings
from ragkit_server.core.errors import UnprocessableError, UpstreamError
from tests.unit.helpers import hit

SOURCES = [hit("Refunds can be issued up to 180 days after the charge.", n=1, title="Refunds")]


async def test_the_extractive_answerer_needs_no_model() -> None:
    answerers = Answerers(Settings(), None, TokenCounter())
    assert answerers.available() == ["extractive"]
    draft = await answerers.answer("extractive", "How long can I refund a charge?", SOURCES)
    assert draft.answerer == "extractive"
    assert "[1]" in draft.text


async def test_unconfigured_model_answerers_are_refused() -> None:
    answerers = Answerers(Settings(), None, TokenCounter())
    with pytest.raises(UnprocessableError) as error:
        await answerers.answer("openai", "q", SOURCES)
    assert error.value.code == "provider_unavailable"


@respx.mock
async def test_openai_compatible_answers_and_reports_usage() -> None:
    settings = Settings(
        llm_provider="openai", llm_model="gpt-test", llm_base_url="https://llm.test/v1"
    )
    route = respx.post("https://llm.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Up to 180 days [1]."}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 7},
            },
        )
    )
    answerers = Answerers(settings, build_chat_client(settings), TokenCounter())
    draft = await answerers.answer("openai", "How long?", SOURCES, model="gpt-other")
    assert draft.text == "Up to 180 days [1]."
    assert draft.answerer == "openai:gpt-other"
    assert (draft.usage.prompt_tokens, draft.usage.completion_tokens) == (120, 7)
    sent = route.calls.last.request
    assert b"<sources>" in sent.content
    assert b"gpt-other" in sent.content


@respx.mock
async def test_ollama_answers_and_counts_usage_when_missing() -> None:
    settings = Settings(
        llm_provider="ollama", llm_model="qwen3:4b", ollama_url="http://ollama.test"
    )
    respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "180 days [1]."}})
    )
    answerers = Answerers(settings, build_chat_client(settings), TokenCounter())
    draft = await answerers.answer("ollama", "How long?", SOURCES)
    assert draft.answerer == "ollama:qwen3:4b"
    assert draft.usage.prompt_tokens > 0
    assert draft.usage.completion_tokens > 0


@respx.mock
async def test_provider_failures_become_upstream_errors() -> None:
    settings = Settings(llm_provider="openai", llm_model="m", llm_base_url="https://llm.test/v1")
    respx.post("https://llm.test/v1/chat/completions").mock(return_value=httpx.Response(503))
    answerers = Answerers(settings, build_chat_client(settings), TokenCounter())
    with pytest.raises(UpstreamError):
        await answerers.answer("openai", "q", SOURCES)


async def test_a_model_answer_without_sources_does_not_call_the_model() -> None:
    settings = Settings(llm_provider="ollama", llm_model="m", ollama_url="http://unreachable.test")
    answerers = Answerers(settings, build_chat_client(settings), TokenCounter())
    draft = await answerers.answer("ollama", "q", [])
    assert "do not answer" in draft.text
