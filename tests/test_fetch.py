import datetime as dt

import httpx
import pytest

from dryline.fetch import Disallowed, Fetcher, raw_path

DAY = dt.date(2026, 10, 17)
NOW = dt.datetime(2026, 10, 17, 13, 0, tzinfo=dt.UTC)


def make_fetcher(tmp_path, handler):
    calls = []

    def wrapped(request: httpx.Request):
        calls.append(str(request.url))
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(wrapped))
    return Fetcher(tmp_path, DAY, client=client, now=lambda: NOW), calls


def test_saves_envelope_and_caches_by_day(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, json={"ok": True})

    f, calls = make_fetcher(tmp_path, handler)
    raw = f.get("nws", "x", "https://api.example.gov/x", params={"a": "1"})
    assert raw.ok and raw.fetched_at == NOW and raw.json_body() == {"ok": True}
    assert raw_path(tmp_path, DAY, "nws", "x").exists()
    again = f.get("nws", "x", "https://api.example.gov/x", params={"a": "1"})
    assert again == raw
    assert calls == ["https://api.example.gov/robots.txt", "https://api.example.gov/x?a=1"]


def test_robots_disallow_blocks_fetch(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, text="secret")

    f, calls = make_fetcher(tmp_path, handler)
    with pytest.raises(Disallowed):
        f.get("pages", "p", "https://site.example.org/private/page")
    assert calls == ["https://site.example.org/robots.txt"]
    assert f.get("pages", "q", "https://site.example.org/public").body == "secret"


def test_network_error_is_recorded_not_raised(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ConnectError("boom")

    f, _ = make_fetcher(tmp_path, handler)
    raw = f.get("nws", "y", "https://api.example.gov/y")
    assert raw.status_code == 0 and not raw.ok


def test_failed_fetch_is_retried_same_day(tmp_path):
    responses = iter([503, 200])

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(next(responses), text="x")

    f, _ = make_fetcher(tmp_path, handler)
    assert f.get("nws", "z", "https://api.example.gov/z").status_code == 503
    f2, _ = make_fetcher(tmp_path, handler)
    assert f2.get("nws", "z", "https://api.example.gov/z").status_code == 200
