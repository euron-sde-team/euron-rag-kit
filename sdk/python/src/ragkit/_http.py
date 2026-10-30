"""The transport: JSON over HTTPS with the API key, retries and the error envelope."""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

from ragkit import __version__
from ragkit.errors import RAGKitError, from_response

GATEWAY_ERRORS = frozenset({502, 503, 504})
IDEMPOTENT = frozenset({"GET", "HEAD", "DELETE"})


class Transport:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "authorization": f"Bearer {api_key}",
                "user-agent": f"euron-ragkit-python/{__version__}",
                "accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        files: Any = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request, retrying with backoff when it is safe to.

        A 429 was rejected before any work happened, so every method is retried. Network
        failures and gateway errors may hide a request that did run, so only idempotent
        methods are retried for those: a retried POST could start a second evaluation run.
        """
        safe = method.upper() in IDEMPOTENT
        attempt = 0
        while True:
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    params={k: v for k, v in (params or {}).items() if v is not None},
                    files=files,
                    data=data,
                )
            except httpx.TransportError as exc:
                if not safe or attempt >= self.max_retries:
                    raise RAGKitError(f"Cannot reach RAGKit: {exc}", code="network_error") from exc
                self._sleep(attempt, None)
                attempt += 1
                continue
            retryable = response.status_code == 429 or (
                safe and response.status_code in GATEWAY_ERRORS
            )
            if retryable and attempt < self.max_retries:
                self._sleep(attempt, response.headers.get("retry-after"))
                attempt += 1
                continue
            return self._parse(response)

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), 30.0)
        else:
            delay = min(0.5 * 2**attempt, 8.0) * (0.5 + random.random() / 2)  # noqa: S311
        time.sleep(delay)

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        body: Any
        if "json" in content_type:
            try:
                body = response.json()
            except ValueError:
                body = None
        else:
            body = response.text
        if response.is_error:
            raise from_response(response.status_code, body)
        return body

    def close(self) -> None:
        self._client.close()
