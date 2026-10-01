from datetime import UTC, datetime

import feedparser
import pytest

from UK_news_scraper.errors import DownloadError
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry import registry

SINCE = datetime(2026, 9, 1, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, tzinfo=UTC)
PAGE = (
    '<article><h3><a href="/news/policy">Official digital policy announcement</a></h3>'
    '<time datetime="2026-09-25"></time><p>Official policy summary.</p></article>'
)


def test_catalog_html_endpoint_failure_preserves_other_endpoint_records(monkeypatch):
    agency = Agency("Official", "Official", "catalog:test", "https://official.example/", news_pages=(
        "https://official.example/unavailable", "https://official.example/news", "https://official.example/archive"
    ))

    def get_text(url):
        if url.endswith("unavailable"):
            raise DownloadError("HTTP 403 Forbidden")
        return PAGE

    monkeypatch.setattr(registry, "catalog_adapter", lambda _: "html_news")
    monkeypatch.setattr(registry, "get_text", get_text)
    scraper = registry.AgencyFeedScraper(agency, UNTIL)
    items = scraper.fetch(SINCE)
    assert len(items) == 1
    assert items[0].link == "https://official.example/news/policy"
    assert scraper.candidate_count == 2
    assert any("403 Forbidden" in warning for warning in scraper.source_warnings)


def test_catalog_html_reports_layout_change_and_all_endpoint_failure(monkeypatch):
    agency = Agency("Official", "Official", "catalog:test", "https://official.example/",
                    news_pages=("https://official.example/news",))
    monkeypatch.setattr(registry, "catalog_adapter", lambda _: "html_news")
    monkeypatch.setattr(registry, "get_text", lambda _: "<h1>News</h1><p>Page layout changed</p>")
    scraper = registry.AgencyFeedScraper(agency, UNTIL)
    assert not scraper.fetch(SINCE)
    assert any("請確認頁面格式" in warning for warning in scraper.source_warnings)

    def fail(_url):
        raise DownloadError("Read timeout")

    monkeypatch.setattr(registry, "get_text", fail)
    with pytest.raises(DownloadError, match="所有官方發布頁讀取失敗"):
        scraper.fetch(SINCE)
    assert any("Read timeout" in warning for warning in scraper.source_warnings)


def test_reviewed_feed_rejects_unrelated_hosts_and_until_boundary(monkeypatch):
    agency = Agency("Official", "Official", "catalog:test", "https://official.example/")
    monkeypatch.setattr(registry, "catalog_adapter", lambda _: "feed")
    xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><id>f</id><title>Official</title>
      <updated>2026-09-25T00:00:00Z</updated><entry><id>one</id>
      <title>Official policy announcement</title><link href="https://unrelated.example/news/one"/>
      <updated>2026-09-25T00:00:00Z</updated></entry></feed>'''
    entry = feedparser.parse(xml).entries[0]
    scraper = registry.AgencyFeedScraper(agency, UNTIL)
    assert scraper._entry_to_news_item(entry, "feed", SINCE) is None
    entry.link = "https://official.example/news/one"
    assert scraper._entry_to_news_item(entry, "feed", SINCE) is not None
    scraper.until = datetime(2026, 9, 25, tzinfo=UTC)
    assert scraper._entry_to_news_item(entry, "feed", SINCE) is None
