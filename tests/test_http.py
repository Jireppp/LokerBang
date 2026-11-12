import httpx
import pytest

from scraper import BlockedError, HttpClient


def test_retries_then_succeeds():
    statuses = [503, 429, 200]
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        code = statuses.pop(0)
        return httpx.Response(code, text="ok" if code == 200 else "err")

    client = HttpClient(
        min_delay=2.0,
        max_delay=5.0,
        max_retries=4,
        backoff_base=2.0,
        sleep=sleeps.append,
        transport=httpx.MockTransport(handler),
    )
    resp = client.get("https://example.com/jobs")
    assert resp.status_code == 200
    assert len(sleeps) == 2
    assert sleeps[0] >= 2.0
    assert sleeps[1] >= 4.0
    client.close()


def test_raises_after_max_retries():
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client = HttpClient(
        max_retries=3,
        backoff_base=2.0,
        sleep=sleeps.append,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get("https://example.com/jobs")
    assert len(sleeps) == 3
    client.close()


def test_403_raises_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    client = HttpClient(
        sleep=lambda _: None,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(BlockedError):
        client.get("https://example.com/jobs")
    client.close()


def test_firewall_html_raises_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><title>Glints - Firewall</title></html>")

    client = HttpClient(
        sleep=lambda _: None,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(BlockedError):
        client.get("https://glints.com/api/v2/graphql")
    client.close()


def test_delay_between_requests_in_range():
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = HttpClient(
        min_delay=2.0,
        max_delay=5.0,
        sleep=sleeps.append,
        transport=httpx.MockTransport(handler),
    )
    client.get("https://example.com/1")
    assert sleeps == []  # no sleep before first request
    client.get("https://example.com/2")
    assert len(sleeps) == 1
    assert 2.0 <= sleeps[0] <= 5.0
    client.close()


def test_user_agent_rotates():
    seen_uas: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        seen_uas.add(request.headers.get("User-Agent", ""))
        return httpx.Response(200, text="ok")

    client = HttpClient(
        sleep=lambda _: None,
        transport=httpx.MockTransport(handler),
    )
    for i in range(12):
        client.get(f"https://example.com/{i}")
    assert len(seen_uas) > 1
    client.close()
