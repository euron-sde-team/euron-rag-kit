"""Answerers: the offline extractive answerer and chat models, behind one interface.

Every answerer takes a question and numbered sources and returns text with [n] citation
markers plus token usage. Model clients speak two wire formats: the OpenAI-compatible Chat
Completions API (OpenAI, Groq, Together, Mistral, DeepSeek, OpenRouter, vLLM, LM Studio and
others) and Ollama's native /api/chat.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from ragkit_server.ai.embeddings import Embedder
from ragkit_server.ai.extractive import answer_units, extractive_answer
from ragkit_server.ai.prompts import answer_messages
from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.core.config import Settings
from ragkit_server.core.errors import UnprocessableError, UpstreamError
from ragkit_server.core.logging import get_logger
from ragkit_server.retrieval.types import Hit

log = get_logger("ragkit.answers")


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True, slots=True)
class Draft:
    text: str
    usage: Usage
    answerer: str


class ChatClient(Protocol):
    provider: str
    default_model: str

    async def complete(
        self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int
    ) -> tuple[str, Usage]: ...

    async def aclose(self) -> None: ...


class OpenAICompatibleClient:
    provider = "openai"

    def __init__(self, settings: Settings) -> None:
        self.default_model = settings.llm_model
        self._temperature = settings.llm_temperature
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"authorization": f"Bearer {key}"} if key else {},
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
        )

    async def complete(
        self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int
    ) -> tuple[str, Usage]:
        body = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = await self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("The model provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("The model provider could not be reached.") from exc
        if response.status_code >= 400:
            log.warning("llm_error", status=response.status_code, detail=response.text[:300])
            raise UpstreamError(f"The model provider returned HTTP {response.status_code}.")
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError("The model provider returned an unexpected response.") from exc
        reported = payload.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(reported.get("prompt_tokens", 0)),
            completion_tokens=int(reported.get("completion_tokens", 0)),
        )
        return str(content).strip(), usage

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaClient:
    provider = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.default_model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/"),
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
        )

    async def complete(
        self, messages: list[dict[str, str]], *, model: str | None = None, max_tokens: int
    ) -> tuple[str, Usage]:
        body = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self._temperature, "num_predict": max_tokens},
        }
        try:
            response = await self._client.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("Ollama timed out.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("Ollama could not be reached.") from exc
        if response.status_code >= 400:
            raise UpstreamError(f"Ollama returned HTTP {response.status_code}.")
        payload = response.json()
        try:
            content = payload["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise UpstreamError("Ollama returned an unexpected response.") from exc
        usage = Usage(
            prompt_tokens=int(payload.get("prompt_eval_count", 0)),
            completion_tokens=int(payload.get("eval_count", 0)),
        )
        return str(content).strip(), usage

    async def aclose(self) -> None:
        await self._client.aclose()


def build_chat_client(settings: Settings) -> ChatClient | None:
    if settings.llm_provider == "openai":
        return OpenAICompatibleClient(settings)
    if settings.llm_provider == "ollama":
        return OllamaClient(settings)
    return None


class Answerers:
    """Every answerer this deployment can run, chosen per request by name."""

    def __init__(self, settings: Settings, client: ChatClient | None, counter: TokenCounter):
        self._settings = settings
        self.client = client
        self._counter = counter

    def available(self) -> list[str]:
        return ["extractive", *([self.client.provider] if self.client else [])]

    def check(self, name: str) -> None:
        if name != "extractive" and (self.client is None or self.client.provider != name):
            raise UnprocessableError(
                f"The {name} answerer is not configured on this deployment. Set LLM_PROVIDER="
                f"{name} and LLM_MODEL, or use the extractive answerer.",
                code="provider_unavailable",
            )

    async def answer(
        self,
        name: str,
        question: str,
        sources: Sequence[Hit],
        *,
        model: str | None = None,
        embedder: Embedder | None = None,
    ) -> Draft:
        self.check(name)
        client = self.client
        if name == "extractive" or client is None:
            return Draft(await self._extractive(question, sources, embedder), Usage(), "extractive")
        label = f"{client.provider}:{model or client.default_model or 'default'}"
        if not sources:
            return Draft("The sources do not answer this question.", Usage(), label)
        messages = answer_messages(question, sources)
        text, usage = await client.complete(
            messages, model=model, max_tokens=self._settings.llm_max_tokens
        )
        # Some servers do not report usage; count it ourselves when missing.
        if not usage.prompt_tokens:
            usage.prompt_tokens = sum(self._counter.count(m["content"]) for m in messages)
        if not usage.completion_tokens:
            usage.completion_tokens = self._counter.count(text)
        return Draft(text, usage, label)

    async def _extractive(
        self, question: str, sources: Sequence[Hit], embedder: Embedder | None
    ) -> str:
        units = answer_units(sources)
        similarities = None
        if embedder is not None and units:
            try:
                vectors = await embedder.embed_documents([unit.text for unit in units])
                similarities = vectors @ await embedder.embed_query(question)
            except Exception:
                log.warning("extractive_semantic_scoring_unavailable")
        return extractive_answer(question, sources, units=units, similarities=similarities).text
