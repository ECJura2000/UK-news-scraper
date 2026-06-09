from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
from bs4 import BeautifulSoup

from UK_news_scraper.main import _run_status
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper, AgencyFetchStatus, FetchAllResult
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
