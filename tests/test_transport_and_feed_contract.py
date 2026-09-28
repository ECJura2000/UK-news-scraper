"""Transport failures and feed discovery remain isolated from live websites."""

from types import SimpleNamespace

import pytest
import requests

from UK_news_scraper import rss
from UK_news_scraper.errors import DownloadError, ParseError
from UK_news_scraper.http import async_client


class Response:
    def __init__(self, text="ok", status_code=200, payload=None):
        self.text = text
        self.status_code = status_code
        self.payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self.payload is None:
            raise requests.JSONDecodeError("invalid", "invalid", 0)
        return self.payload


def test_http_client_preserves_text_json_and_failure_boundaries(monkeypatch):
    seen = []

    class Session:
        def get(self, url, **kwargs):
            seen.append((url, kwargs))
            return Response("official text", payload={"result": "ok"})

    monkeypatch.setattr(async_client, "get_session", Session)
    assert async_client.get_text("https://official.example/page", timeout=3) == "official text"
    assert async_client.get_json("https://official.example/api") == {"result": "ok"}
    assert seen[0][1]["timeout"] == 3
    assert seen[1][1]["headers"]["Accept"] == "application/json"

    class FailingSession:
        def get(self, _url, **_kwargs):
            raise requests.Timeout("offline timeout")

    monkeypatch.setattr(async_client, "get_session", FailingSession)
    with pytest.raises(DownloadError):
        async_client.get_text("https://official.example/page")

    monkeypatch.setattr(
        async_client, "get_session", lambda: SimpleNamespace(get=lambda *_args, **_kwargs: Response(status_code=503))
    )
    with pytest.raises(DownloadError):
        async_client.get_text("https://official.example/page")

    monkeypatch.setattr(async_client, "get_session", lambda: SimpleNamespace(get=lambda *_args, **_kwargs: Response()))
    with pytest.raises(ParseError):
        async_client.get_json("https://official.example/api")


def test_challenge_fallback_is_used_only_for_challenge_response(monkeypatch):
    monkeypatch.setattr(
        async_client,
        "get_session",
        lambda: SimpleNamespace(
            get=lambda *_args, **_kwargs: Response("Just a moment ... Cloudflare", status_code=403)
        ),
    )
    monkeypatch.setattr(async_client, "_get_text_with_browser_tls", lambda url, timeout: f"fallback:{url}:{timeout}")
    assert async_client.get_text("https://official.example", timeout=2) == "fallback:https://official.example:2"
    assert not async_client._looks_like_cloudflare_challenge("ordinary forbidden")


def test_browser_tls_adapter_rejects_unsolved_challenge(monkeypatch):
    from curl_cffi import requests as curl_requests

    monkeypatch.setattr(curl_requests, "get", lambda *_args, **_kwargs: Response("Just a moment Cloudflare", 403))
    with pytest.raises(requests.HTTPError, match="Cloudflare challenge"):
        async_client._get_text_with_browser_tls("https://official.example", 2)
    monkeypatch.setattr(curl_requests, "get", lambda *_args, **_kwargs: Response("official recovered"))
    assert async_client._get_text_with_browser_tls("https://official.example", 2) == "official recovered"


def test_feed_parser_and_discovery_validate_untrusted_content(monkeypatch):
    monkeypatch.setattr(rss, "get_text", lambda _url: "<rss>fixture</rss>")
    monkeypatch.setattr(rss.feedparser, "parse", lambda _text: SimpleNamespace(bozo=False, entries=[{"title": "news"}]))
    assert len(rss.parse_feed("https://official.example/feed").entries) == 1

    monkeypatch.setattr(
        rss.feedparser, "parse", lambda _text: SimpleNamespace(bozo=True, entries=[], bozo_exception="bad XML")
    )
    with pytest.raises(ValueError, match="bad XML"):
        rss.parse_feed("https://official.example/feed")

    html = """<html><head>
      <link rel="alternate" type="application/rss+xml" href="/feed.xml">
      <link rel="alternate" type="application/rss+xml" href="/feed.xml">
      <link rel="stylesheet" type="text/css" href="/style.css">
      <link rel="alternate" type="application/atom+xml" href="https://official.example/atom">
    </head></html>"""
    monkeypatch.setattr(rss, "get_text", lambda _url: html)
    assert rss.discover_feed_urls("https://official.example/news") == [
        "https://official.example/feed.xml",
        "https://official.example/atom",
    ]
    monkeypatch.setattr(rss, "get_text", lambda _url: (_ for _ in ()).throw(OSError("offline")))
    assert rss.discover_feed_urls("https://official.example/news") == []
