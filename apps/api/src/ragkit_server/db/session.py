"""Async engines and the session factory.

- The pgvector codec is registered on every application connection, so embeddings travel
  in binary form (numpy arrays in, numpy arrays out) instead of being formatted as text.
- With DATABASE_SECRET_ARN set (AWS), each new connection reads the password from the
  RDS-managed secret, cached for a minute, so a password rotation needs no redeploy.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from pgvector.asyncpg import register_vector
from sqlalchemy import event, pool, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ragkit_server.core.config import Settings
from ragkit_server.integrations import aws

_PASSWORD_TTL_S = 60


class SecretPassword:
    """The current database password from Secrets Manager, refreshed at most once a minute."""

    def __init__(self, settings: Settings, secret_arn: str) -> None:
        self._client = aws.secrets_client(settings)
        self._arn = secret_arn
        self._value: str | None = None
        self._fetched = 0.0
        self._lock = threading.Lock()

    def current(self) -> str:
        with self._lock:
            if self._value is None or time.monotonic() - self._fetched > _PASSWORD_TTL_S:
                secret = self._client.get_secret_value(SecretId=self._arn)
                self._value = str(json.loads(secret["SecretString"])["password"])
                self._fetched = time.monotonic()
            return self._value

    def inject(self, _dialect: Any, _record: Any, _cargs: Any, cparams: dict[str, Any]) -> None:
        cparams["password"] = self.current()


def create_engine(
    settings: Settings, *, pooled: bool = True, vector_codec: bool = True
) -> AsyncEngine:
    options: dict[str, Any] = {
        "pool_pre_ping": True,
        "echo": settings.database_echo,
        # JIT compilation costs more than it saves on short OLTP queries.
        "connect_args": {"server_settings": {"application_name": "ragkit", "jit": "off"}},
    }
    if pooled:
        options |= {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
            "pool_recycle": 1800,
        }
    else:
        options["poolclass"] = pool.NullPool
    engine = create_async_engine(settings.database_url, **options)
    if settings.database_secret_arn:
        password = SecretPassword(settings, settings.database_secret_arn)
        event.listen(engine.sync_engine, "do_connect", password.inject)
    if vector_codec:
        event.listen(engine.sync_engine, "connect", _register_codecs)
    return engine


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine: AsyncEngine = create_engine(settings)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    def session(self) -> AsyncSession:
        return self.sessionmaker()

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()


def _register_codecs(dbapi_connection: Any, _: Any) -> None:
    dbapi_connection.run_async(register_vector)
