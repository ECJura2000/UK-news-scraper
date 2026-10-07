from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import feedparser
import pytest
from openpyxl import load_workbook

from UK_news_scraper.app_service import RunRequest, execute_run
from UK_news_scraper.article_links import is_agency_homepage
from UK_news_scraper.config import AGENCIES
from UK_news_scraper.models import Agency
from UK_news_scraper.profiles import default_profile
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper
from UK_news_scraper.scrapers.ministry.status import AgencyFetchStatus, FetchAllResult

FIXTURE = Path(__file__).parent / "fixtures" / "agency_homepage_guard.xml"
SINCE = datetime(2026, 9, 23, tzinfo=UTC)
UNTIL = datetime(2026, 10, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("link", "homepage", "expected"),
    [
        ("https://www.gov.uk/government/organisations/bist/?q=1#top", "", True),
        ("https://official.example/?q=1", "https://www.official.example", True),
        ("https://www.gov.uk/government/organisations/bist/about/research", "", False),
        ("https://www.gov.uk/government/news/ai-policy", "", False),
        ("https://other.example/government/organisations/bist", "", False),
        ("https://official.example/news/ai", "https://official.example", False),
    ],
)
def test_homepage_guard_preserves_articles(link, homepage, expected):
    assert is_agency_homepage(link, homepage) is expected


def test_feed_excludes_homepage_without_dropping_guidance(monkeypatch):
    agency = replace(next(a for a in AGENCIES if a.short_name == "BIST"), official_pages=())
    feed = feedparser.parse(FIXTURE.read_bytes())
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feed)
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.discover_feed_urls", lambda _: [])
    scraper = AgencyFeedScraper(agency, until=UNTIL)
    items = scraper.fetch(SINCE)
    assert len(items) == 2
    assert {x.content_type for x in items} == {"news", "guidance"}
    assert scraper.candidate_count == 3  # two dated articles plus one undated parser candidate
    assert all(not is_agency_homepage(x.link) for x in items)


def test_output_guard_removes_legacy_homepage_and_preserves_logical_counts(monkeypatch, tmp_path):
    agency = next(a for a in AGENCIES if a.short_name == "BIST")
    scraper = AgencyFeedScraper(agency, until=UNTIL)
    feed = feedparser.parse(FIXTURE.read_bytes())
    records = [scraper._entry_to_news_item(entry, "fixture", SINCE) for entry in feed.entries]
    articles = [x for x in records if x]
    articles[0].source_feed = "https://news.google.com/rss/search?q=official"
    # Simulate an older adapter/cache containing the formerly accepted homepage.
    homepage = replace(articles[0], title="Department homepage", link=agency.homepage)
    fetched = FetchAllResult(
        items=[homepage, *articles],
        statuses=[
            AgencyFetchStatus(agency_name=agency.display_name, source_name="BIST", success=True, item_count=3),
        ],
    )
    monkeypatch.setattr("UK_news_scraper.app_service.fetch_all_with_status", lambda *_args, **_kwargs: fetched)
    monkeypatch.setattr("UK_news_scraper.excel_exporter._translate_texts", lambda *_args, **_kwargs: {})
    profile = replace(default_profile(), selected_sources=("BIST",))
    result = execute_run(RunRequest(date(2026, 9, 23), date(2026, 10, 7), output_dir=tmp_path, profile=profile))
    assert result.summary.all_news_count == 2
    assert result.summary.source_health[0].item_count == 2
    assert all(not is_agency_homepage(x.link) for x in result.all_items)
    book = load_workbook(result.workbook_path)
    links = [cell.hyperlink.target for row in book["全部新聞"] for cell in row if cell.hyperlink]
    assert len(links) == 2
    assert all(not is_agency_homepage(link) for link in links)
    assert any(row[0] == "備援資料日期" and "未核對官方發布日期" in row[1] for row in book["篩選設定"].values)
    book.close()


def test_google_fallback_rejects_wrong_publisher_and_out_of_period_dates(monkeypatch):
    agency = Agency("Ofcom", "Ofcom", "Ofcom", "https://www.ofcom.org.uk")
    scraper = AgencyFeedScraper(agency, until=UNTIL)
    xml = """<rss version="2.0"><channel><title>Search</title>
    <link>https://news.google.com</link><description>Search</description>
    <item>
    <title>Online safety announcement - www.ofcom.org.uk</title>
    <link>https://news.google.com/rss/articles/good</link>
    <pubDate>Fri, 02 Oct 2026 00:00:00 GMT</pubDate>
    <source url="https://www.ofcom.org.uk">Ofcom</source></item>
    <item>
    <title>Spoofed online safety news - www.ofcom.org.uk</title>
    <link>https://news.google.com/rss/articles/spoof</link>
    <pubDate>Fri, 02 Oct 2026 00:00:00 GMT</pubDate>
    <source url="https://ofcom.org.uk.evil.example">Ofcom</source></item>
    <item>
    <title>Future online safety news - www.ofcom.org.uk</title>
    <link>https://news.google.com/rss/articles/future</link>
    <pubDate>Fri, 09 Oct 2026 00:00:00 GMT</pubDate>
    <source url="https://www.ofcom.org.uk">Ofcom</source></item>
    </channel></rss>"""
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feedparser.parse(xml))
    items = scraper._fetch_google_news_fallback(SINCE)
    assert [x.link for x in items] == ["https://news.google.com/rss/articles/good"]
    assert any("發布者不符" in warning for warning in scraper.source_warnings)
    assert any("未核對官方發布日期" in warning for warning in scraper.source_warnings)


def test_homepage_update_date_is_not_a_parser_failure(monkeypatch):
    agency = next(a for a in AGENCIES if a.short_name == "BIST")
    scraper = AgencyFeedScraper(agency, until=UNTIL)
    monkeypatch.setattr(
        "UK_news_scraper.scrapers.ministry.registry.get_text",
        lambda _: '<h1>Department homepage</h1><meta property="article:published_time" content="2026-10-01T00:00:00Z">',
    )
    items, _, successes = scraper._fetch_official_pages(SINCE)
    assert items == []
    assert successes == 1
    assert scraper.candidate_count == 0
    assert scraper.source_warnings == []
