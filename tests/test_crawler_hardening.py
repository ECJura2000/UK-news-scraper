import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic, sleep

import feedparser
import pytest
import requests

from UK_news_scraper.errors import DownloadError
from UK_news_scraper.http import async_client
from UK_news_scraper.models import Agency, SourceHealth
from UK_news_scraper.observability import summarize_source_health
from UK_news_scraper.provenance import canonical_url
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper


FIXTURES = Path(__file__).parent / "fixtures"


def test_shared_source_contract():
    fixture = json.loads((FIXTURES / "source_contract_v1.json").read_text(encoding="utf-8"))
    summary = summarize_source_health(SourceHealth(**source) for source in fixture["health"])
    assert vars(summary) == {**fixture["expected_observability"], "alerts": tuple(fixture["expected_observability"]["alerts"])}
    for example in fixture["canonical_urls"]:
        assert canonical_url(example["raw"]) == example["expected"]


def test_feed_with_valid_and_malformed_entries_preserves_valid_item(monkeypatch):
    agency = Agency("官方機關", "Official", "court-test:judgments", "https://official.example", feeds=("https://official.example/feed",))
    feed = feedparser.parse((FIXTURES / "source_parser_v1.xml").read_bytes())
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feed)
    scraper = AgencyFeedScraper(agency)
    items = scraper.fetch(datetime(2026, 9, 23, tzinfo=timezone.utc))
    assert len(items) == 1
    assert scraper.candidate_count == 2
    assert items[0].content_type == "judgment"


def test_feed_with_only_malformed_in_range_entry_is_degraded(monkeypatch):
    agency = Agency("官方機關", "Official", "court-test:judgments", "https://official.example", feeds=("https://official.example/feed",))
    feed = feedparser.parse((FIXTURES / "source_parser_v1.xml").read_bytes())
    feed.entries = feed.entries[1:]
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feed)
    scraper = AgencyFeedScraper(agency)
    items = scraper.fetch(datetime(2026, 9, 23, tzinfo=timezone.utc))
    assert items == []
    assert any("解析為零筆" in warning for warning in scraper.source_warnings)


def test_official_page_with_recent_date_but_no_records_warns(monkeypatch):
    agency = Agency("官方機關", "Official", "TEST", "https://official.example", official_pages=("https://official.example/archive",))
    monkeypatch.setattr(
        "UK_news_scraper.scrapers.ministry.registry.get_text",
        lambda _: "<html><body><h1>Archive</h1><time datetime='2026-09-23'>23 September 2026</time></body></html>",
    )
    scraper = AgencyFeedScraper(agency, until=datetime(2026, 9, 24, tzinfo=timezone.utc))
    assert scraper.fetch(datetime(2026, 9, 23, tzinfo=timezone.utc)) == []
    assert scraper.candidate_count == 1
    assert any("解析為零筆" in warning for warning in scraper.source_warnings)


def _response(status: int, body: bytes = b"ok", retry_after: str = "") -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body
    response._content_consumed = True
    response.url = "https://official.example/feed"
    if retry_after:
        response.headers["Retry-After"] = retry_after
    return response


def test_retry_after_is_bounded_by_run_deadline(monkeypatch):
    class Session:
        def get(self, *_args, **_kwargs):
            return _response(429, retry_after="100")

    monkeypatch.setattr(async_client, "get_session", lambda: Session())
    with async_client.request_deadline(monotonic() + 1):
        with pytest.raises(DownloadError, match="延後重試"):
            async_client.get_text("https://official.example/feed")


def test_requests_to_same_host_never_exceed_two_in_flight(monkeypatch):
    lock = Lock()
    active = 0
    peak = 0

    class Session:
        def get(self, *_args, **_kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(active, peak)
            sleep(0.03)
            with lock:
                active -= 1
            return _response(200)

    monkeypatch.setattr(async_client, "get_session", lambda: Session())
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(async_client.get_text, ["https://official.example/feed"] * 6)) == ["ok"] * 6
    assert peak == 2
