"""Fetch URL sources without letting a URL reach places it must not.

A URL loader is a server-side request forgery primitive by construction, so every hop is
checked before it is requested:

- only http and https, on the default ports or an unprivileged port (1024 and above),
- the host must resolve, and every address it resolves to must be globally routable (no
  private, loopback, link-local, shared, reserved or multicast ranges, which also covers
  the cloud metadata address 169.254.169.254), unless URL_FETCH_ALLOW_PRIVATE is set,
- redirects are followed by hand, at most three, each re-checked,
- the body is capped at MAX_UPLOAD_MB and the whole fetch at URL_FETCH_TIMEOUT_S.

Residual risk: DNS can change between the check and the connection (rebinding). The fetch
response is stored as a document, never echoed to the caller, which limits what an attacker
learns; see docs/architecture/threat-model.md.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import anyio
import httpx

from ragkit_server import __version__
from ragkit_server.core.config import Settings
from ragkit_server.core.errors import AppError

MAX_REDIRECTS = 3
USER_AGENT = f"EuronRAGKit/{__version__} (+https://github.com/euron-sde-team/euron-rag-kit)"


class FetchError(AppError):
    status_code = 422
    code = "fetch_failed"
    message = "The URL could not be fetched."


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    content_type: str
    data: bytes


def check_url_shape(url: str) -> tuple[str, int | None]:
    """The host and port of a URL that is allowed to be requested at all."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs can be loaded.", code="invalid_url")
    if not parts.hostname:
        raise FetchError("The URL has no host.", code="invalid_url")
    if parts.username or parts.password:
        raise FetchError("URLs with credentials are not accepted.", code="invalid_url")
    try:
        port = parts.port
    except ValueError as exc:
        raise FetchError("The URL has an invalid port.", code="invalid_url") from exc
    if port is not None and port not in (80, 443) and port < 1024:
        raise FetchError("That port is not allowed for URL sources.", code="invalid_url")
    return parts.hostname, port


def is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class UrlFetcher:
    def __init__(self, settings: Settings) -> None:
        self._allow_private = settings.url_fetch_allow_private
        self._max_bytes = settings.max_upload_bytes
        self._timeout = settings.url_fetch_timeout_s
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.url_fetch_timeout_s, connect=10.0),
            headers={
                "user-agent": USER_AGENT,
                "accept": "text/html, text/markdown, "
                "text/plain, text/csv, application/pdf;q=0.9, */*;q=0.1",
            },
            follow_redirects=False,
        )

    async def _check_host(self, host: str, port: int | None) -> None:
        if self._allow_private:
            return
        try:
            infos = await anyio.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise FetchError(f"The host {host} could not be resolved.") from exc
        addresses = {str(info[4][0]) for info in infos}
        if not addresses or not all(is_public_address(a) for a in addresses):
            raise FetchError(
                "That address is not public, so it cannot be loaded.", code="url_not_allowed"
            )

    async def fetch(self, url: str) -> FetchedPage:
        current = url.strip()
        with anyio.fail_after(self._timeout * 2):
            for _ in range(MAX_REDIRECTS + 1):
                host, port = check_url_shape(current)
                await self._check_host(host, port)
                try:
                    async with self._client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise FetchError("A redirect had no location.")
                            current = urljoin(current, location)
                            continue
                        if response.status_code >= 400:
                            raise FetchError(f"The server answered HTTP {response.status_code}.")
                        content_type = (
                            response.headers.get("content-type", "").split(";")[0].strip().lower()
                        )
                        data = await self._read_capped(response)
                        return FetchedPage(url=current, content_type=content_type, data=data)
                except httpx.HTTPError as exc:
                    raise FetchError(
                        f"The URL could not be fetched ({type(exc).__name__})."
                    ) from exc
        raise FetchError("The URL redirected too many times.")

    async def _read_capped(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self._max_bytes:
                raise FetchError(
                    "The page is larger than this deployment allows.", code="payload_too_large"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def aclose(self) -> None:
        await self._client.aclose()
