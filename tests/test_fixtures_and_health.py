from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
from bs4 import BeautifulSoup

from UK_news_scraper.main import _run_status
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry.registry import (
    AgencyFeedScraper,
    AgencyFetchStatus,
    FetchAllResult,
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
                agency_name="DSIT",
                source_name="DSIT",
                success=True,
                warning="DSIT 筆數異常",
            )
        ],
    )
    parliament = ParliamentFetchResult(items=[], source_mode="RSS")

    status, warnings = _run_status(ministry, parliament)

    assert status == "degraded"
    assert "DSIT 筆數異常" in warnings


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


def test_low_frequency_source_does_not_warn_for_zero_items():
    since = datetime.now(timezone.utc) - timedelta(days=14)

    assert _health_warning("AISI", [], since) == ""
    assert "低於健康門檻" in _health_warning("DSIT", [], since)
