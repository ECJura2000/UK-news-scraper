from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import feedparser
from bs4 import BeautifulSoup

from UK_news_scraper.main import _run_status
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry.registry import (
    AgencyFeedScraper,
    AgencyFetchStatus,
    FetchAllResult,
    OFCOM_GOOGLE_NEWS_QUERIES,
    _health_warning,
    _is_electoral_commission_google_news_title,
)
from UK_news_scraper.scrapers.parliament import research_briefings
from UK_news_scraper.scrapers.parliament.research_briefings import ParliamentFetchResult


FIXTURES = Path(__file__).parent / "fixtures"


def test_electoral_commission_fixture_parser():
    agency = Agency("選舉委員會", "Electoral Commission", "Electoral Commission", "https://example.com")
    scraper = AgencyFeedScraper(agency)
    soup = BeautifulSoup((FIXTURES / "electoral_commission.html").read_text(), "html.parser")

    items = scraper._extract_electoral_commission_items(
        soup,
        "https://www.electoralcommission.org.uk/news",
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert len(items) == 1
    assert items[0].link == "https://www.electoralcommission.org.uk/news/sample"


def test_official_page_parser_captures_ncsc_guidance_page():
    agency = Agency(
        "國家網路安全中心",
        "National Cyber Security Centre",
        "NCSC",
        "https://www.ncsc.gov.uk/",
        official_pages=("https://www.ncsc.gov.uk/collection/recovering",),
    )
    scraper = AgencyFeedScraper(agency)
    soup = BeautifulSoup(
        """
        <html><head><meta name="description" content="Practical recovery guidance."></head>
        <body><main><h1>Recovering from a highly disruptive cyber attack</h1>
        <time datetime="2026-07-28">28 July 2026</time></main></body></html>
        """,
        "html.parser",
    )

    items = scraper._extract_official_page_items(
        soup,
        "https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering",
        datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert len(items) == 1
    assert items[0].published_at.date().isoformat() == "2026-07-28"
    assert items[0].content_type == "guidance"
    assert items[0].link.endswith("/recovering")


def test_official_pages_are_fetched_even_when_rss_has_items(monkeypatch):
    agency = Agency(
        "測試機關",
        "Test Agency",
        "TEST",
        "https://official.example",
        feeds=("https://official.example/feed.xml",),
        official_pages=("https://official.example/guidance/sample",),
    )
    scraper = AgencyFeedScraper(agency)
    feed = feedparser.parse(
        """
        <rss version="2.0"><channel><item>
        <title>RSS cyber news</title><link>https://official.example/news/rss</link>
        <pubDate>Tue, 28 Jul 2026 12:00:00 GMT</pubDate>
        </item></channel></rss>
        """
    )
    calls = []
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feed)
    monkeypatch.setattr(
        "UK_news_scraper.scrapers.ministry.registry.get_text",
        lambda url: calls.append(url) or "<h1>Official guidance</h1><time datetime='2026-07-28'>28 July 2026</time>",
    )

    items = scraper.fetch(datetime(2026, 7, 1, tzinfo=timezone.utc))

    assert calls == ["https://official.example/guidance/sample"]
    assert {item.content_type for item in items} == {"news", "guidance"}


def test_official_page_failure_is_retained_as_warning_when_rss_succeeds(monkeypatch):
    agency = Agency(
        "測試機關",
        "Test Agency",
        "TEST",
        "https://official.example",
        feeds=("https://official.example/feed.xml",),
        official_pages=("https://official.example/guidance/sample",),
    )
    scraper = AgencyFeedScraper(agency)
    feed = feedparser.parse(
        """<rss version="2.0"><channel><item><title>RSS news</title>
        <link>https://official.example/news/rss</link><pubDate>Tue, 28 Jul 2026 12:00:00 GMT</pubDate>
        </item></channel></rss>"""
    )
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feed)

    def fail(_):
        raise RuntimeError("temporary page failure")

    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_text", fail)

    items = scraper.fetch(datetime(2026, 7, 1, tzinfo=timezone.utc))

    assert len(items) == 1
    assert scraper.source_warnings


def test_commons_rss_fixture_parser(monkeypatch):
    feed = feedparser.parse((FIXTURES / "commons_feed.xml").read_bytes())
    monkeypatch.setattr(research_briefings, "parse_feed", lambda _: feed)

    items = research_briefings._fetch_rss(
        "House of Commons Library",
        "fixture://commons",
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert len(items) == 1
    assert items[0].identifier == "CBP-1234"


def test_commons_rss_paginates_until_an_old_page(monkeypatch):
    recent = feedparser.parse((FIXTURES / "commons_feed.xml").read_bytes())
    old_xml = (FIXTURES / "commons_feed.xml").read_text().replace(
        "Mon, 08 Jun 2026 09:00:00 GMT",
        "Mon, 01 Jun 2026 09:00:00 GMT",
    )
    old = feedparser.parse(old_xml)
    calls: list[str] = []

    def parse_page(url):
        calls.append(url)
        feed = recent if len(calls) == 1 else old
        feed.entries = list(feed.entries) * 10
        return feed

    monkeypatch.setattr(research_briefings, "parse_feed", parse_page)
    items = research_briefings._fetch_rss(
        "House of Commons Library",
        "https://example.com/feed/",
        datetime(2026, 6, 5, tzinfo=timezone.utc),
    )

    assert calls == ["https://example.com/feed/", "https://example.com/feed/?paged=2"]
    assert len(items) == 1


def test_health_warning_degrades_run():
    ministry = FetchAllResult(
        items=[],
        statuses=[
            AgencyFetchStatus(
                agency_name="BIST",
                source_name="BIST",
                success=True,
                warning="BIST 筆數異常",
            )
        ],
    )
    parliament = ParliamentFetchResult(items=[], source_mode="RSS")

    status, warnings = _run_status(ministry, parliament)

    assert status == "degraded"
    assert "BIST 筆數異常" in warnings


def test_stale_critical_parliament_source_has_warning():
    old_item = research_briefings.ParliamentBriefing(
        published_at=datetime.now(timezone.utc) - timedelta(days=20),
        chamber="House of Commons",
        publisher="House of Commons Library",
        title="Old briefing",
        summary="",
        identifier="CBP-1",
        webpage_url="https://example.com/old",
    )

    health = research_briefings._source_health(
        "Commons RSS",
        True,
        True,
        [old_item],
        0.1,
        since=datetime.now(timezone.utc) - timedelta(days=14),
        maximum_age_days=14,
    )

    assert "最新資料已超過" in health.warning


def test_electoral_commission_google_news_filter_removes_database_noise():
    assert _is_electoral_commission_google_news_title(
        "Political parties accept £24.7m in donations in Q1 2026"
    )
    assert not _is_electoral_commission_google_news_title("Search criteria")
    assert not _is_electoral_commission_google_news_title("Donation summary")


def test_ofcom_google_news_fallback_uses_multiple_queries(monkeypatch):
    agency = Agency("英國通訊管理局", "Office of Communications", "Ofcom", "https://example.com")
    scraper = AgencyFeedScraper(agency)
    since = datetime(2026, 6, 21, tzinfo=timezone.utc)
    calls: list[str] = []

    def make_feed(item_title: str | None = None):
        if item_title is None:
            xml = "<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel></channel></rss>"
        else:
            xml = (
                "<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel><item>"
                f"<title>{escape(item_title)}</title>"
                "<link>https://news.google.com/rss/articles/test</link>"
                "<pubDate>Thu, 02 Jul 2026 07:00:00 GMT</pubDate>"
                "<description>summary</description></item></channel></rss>"
            )
        return feedparser.parse(xml)

    def fake_parse_feed(url: str):
        calls.append(url)
        query = parse_qs(urlparse(url).query).get("q", [""])[0]
        query_text = unquote(query)
        if query_text == 'site:ofcom.org.uk "Ofcom consultation"':
            return make_feed("Ofcom consultation update - www.ofcom.org.uk")
        return make_feed()

    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", fake_parse_feed)

    items = scraper._fetch_google_news_fallback(since)

    assert len(calls) == len(OFCOM_GOOGLE_NEWS_QUERIES)
    assert len(items) == 1
    assert items[0].title == "Ofcom consultation update"


def test_low_frequency_source_does_not_warn_for_zero_items():
    since = datetime.now(timezone.utc) - timedelta(days=14)

    assert _health_warning("AISI", [], since) == ""
    assert "低於健康門檻" in _health_warning("BIST", [], since)
