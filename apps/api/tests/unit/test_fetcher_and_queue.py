import asyncio
import uuid

import httpx
import pytest
import respx

from ragkit_server.core.config import Settings
from ragkit_server.integrations.fetcher import (
    FetchError,
    UrlFetcher,
    check_url_shape,
    is_public_address,
)
from ragkit_server.integrations.queue import InlineQueue, Job


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "http:///nohost",
        "https://user:pass@example.com/",
        "http://example.com:22/",
    ],
)
def test_url_shapes_that_are_never_fetched(url: str) -> None:
    with pytest.raises(FetchError):
        check_url_shape(url)


def test_allowed_url_shapes() -> None:
    assert check_url_shape("https://docs.example.com/guide") == ("docs.example.com", None)
    assert check_url_shape("http://docs.example.com:8080/a") == ("docs.example.com", 8080)


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.216.34", True),
        ("10.0.0.5", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),
        ("100.64.1.1", False),
        ("::1", False),
        ("::ffff:10.0.0.1", False),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
    ],
)
def test_only_global_addresses_are_public(address: str, public: bool) -> None:
    assert is_public_address(address) is public


async def test_private_hosts_are_refused_before_any_request() -> None:
    fetcher = UrlFetcher(Settings())
    with respx.mock(assert_all_called=False) as router:
        route = router.get("http://localhost:8080/secret").mock(return_value=httpx.Response(200))
        with pytest.raises(FetchError) as error:
            await fetcher.fetch("http://localhost:8080/secret")
        assert error.value.code == "url_not_allowed"
        assert not route.called
    await fetcher.aclose()


async def test_redirects_are_followed_and_rechecked() -> None:
    fetcher = UrlFetcher(Settings(url_fetch_allow_private=True))
    with respx.mock() as router:
        router.get("http://docs.test/old").mock(
            return_value=httpx.Response(301, headers={"location": "/new"})
        )
        router.get("http://docs.test/new").mock(
            return_value=httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text="<h1>Hi</h1>"
            )
        )
        page = await fetcher.fetch("http://docs.test/old")
    assert page.url == "http://docs.test/new"
    assert page.content_type == "text/html"
    assert page.data == b"<h1>Hi</h1>"
    with respx.mock() as router:
        router.get("http://docs.test/loop").mock(
            return_value=httpx.Response(302, headers={"location": "ftp://docs.test/file"})
        )
        with pytest.raises(FetchError):
            await fetcher.fetch("http://docs.test/loop")
    await fetcher.aclose()


async def test_errors_and_oversized_bodies_are_refused() -> None:
    fetcher = UrlFetcher(Settings(url_fetch_allow_private=True, max_upload_mb=1))
    with respx.mock() as router:
        router.get("http://docs.test/missing").mock(return_value=httpx.Response(404))
        router.get("http://docs.test/huge").mock(
            return_value=httpx.Response(200, content=b"x" * (1024 * 1024 + 1))
        )
        with pytest.raises(FetchError, match="HTTP 404"):
            await fetcher.fetch("http://docs.test/missing")
        with pytest.raises(FetchError) as error:
            await fetcher.fetch("http://docs.test/huge")
        assert error.value.code == "payload_too_large"
    await fetcher.aclose()


def test_jobs_round_trip_and_reject_malformed_messages() -> None:
    project, document, index, run = (uuid.uuid4() for _ in range(4))
    for job in (
        Job.parse(project, document),
        Job.index(project, index, document),
        Job.evaluate(project, run),
    ):
        assert Job.decode(job.encode()) == job
    with pytest.raises(ValueError, match="unknown job kind"):
        Job.decode(f'{{"kind": "launch", "project_id": "{project}"}}')
    with pytest.raises(ValueError, match="missing"):
        Job.decode(f'{{"kind": "index", "project_id": "{project}", "index_id": "{index}"}}')


async def test_the_inline_queue_runs_jobs_in_order_including_follow_ups() -> None:
    queue = InlineQueue()
    seen: list[str] = []
    project = uuid.uuid4()

    async def handler(job: Job) -> None:
        seen.append(job.kind)
        await asyncio.sleep(0)
        if job.kind == "parse":
            await queue.enqueue(Job.index(project, uuid.uuid4(), uuid.uuid4()))
        if job.kind == "eval":
            raise RuntimeError("a failing job does not stop the queue")

    queue.bind(handler)
    await queue.enqueue(Job.parse(project, uuid.uuid4()))
    await queue.enqueue(Job.evaluate(project, uuid.uuid4()))
    await queue.enqueue(Job.parse(project, uuid.uuid4()))
    await queue.drain()
    assert seen == ["parse", "eval", "parse", "index", "index"]
    assert await queue.backlog() == 0
