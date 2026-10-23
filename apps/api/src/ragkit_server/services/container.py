"""Process-wide infrastructure, built once at startup and shared by every request.

Services are cheap objects created per request around one database session; everything
expensive (connection pools, embedding and reranking models, HTTP clients) lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from ragkit_server.ai.answerers import Answerers, ChatClient, build_chat_client
from ragkit_server.ai.embeddings import EmbedderPool
from ragkit_server.ai.judge import ModelJudge
from ragkit_server.ai.tokens import TokenCounter
from ragkit_server.core.config import Settings
from ragkit_server.core.ratelimit import RateLimiter
from ragkit_server.db.session import Database
from ragkit_server.integrations.fetcher import UrlFetcher
from ragkit_server.integrations.queue import InlineQueue, SqsQueue, build_queue
from ragkit_server.integrations.storage import Storage, build_storage
from ragkit_server.retrieval.rerankers import RerankerPool


@dataclass
class Container:
    settings: Settings
    db: Database
    redis: Redis
    storage: Storage
    queue: InlineQueue | SqsQueue
    fetcher: UrlFetcher
    tokens: TokenCounter
    embedders: EmbedderPool
    rerankers: RerankerPool
    chat_client: ChatClient | None
    answerers: Answerers
    judge: ModelJudge | None
    limiter: RateLimiter

    async def close(self) -> None:
        if self.chat_client is not None:
            await self.chat_client.aclose()
        await self.embedders.aclose()
        await self.fetcher.aclose()
        await self.redis.aclose()
        await self.db.dispose()

    async def warm_up(self) -> None:
        """Load the bundled local models, so the first query is not the slow one."""
        if not self.settings.warm_models:
            return
        await self.embedders.warm_up([self.settings.default_embedding_model])
        await self.rerankers.warm_up()


def build_container(settings: Settings) -> Container:
    redis = Redis.from_url(
        settings.redis_url, decode_responses=False, health_check_interval=30, socket_timeout=5
    )
    tokens = TokenCounter(settings.tokenizer)
    chat_client = build_chat_client(settings)
    return Container(
        settings=settings,
        db=Database(settings),
        redis=redis,
        storage=build_storage(settings),
        queue=build_queue(settings),
        fetcher=UrlFetcher(settings),
        tokens=tokens,
        embedders=EmbedderPool(settings, redis),
        rerankers=RerankerPool(settings.reranker_model, settings.embeddings_cache_dir),
        chat_client=chat_client,
        answerers=Answerers(settings, chat_client, tokens),
        judge=ModelJudge(chat_client, settings.judge_model_name) if chat_client else None,
        limiter=RateLimiter(redis),
    )
