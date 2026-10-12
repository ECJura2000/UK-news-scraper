from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import feedparser

from scripts.smoke_sources import SOURCES, WEEKLY_AGENCIES, inspect_results
from UK_news_scraper.models import SourceHealth
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper
from UK_news_scraper.scrapers.parliament.research_briefings import _fetch_rss

SINCE = datetime(2026, 6, 1, tzinfo=UTC)
UNTIL = datetime(2026, 7, 1, tzinfo=UTC)


def results(items=(), health=()):
    return SimpleNamespace(items=list(items), source_health=list(health))


def test_smoke_sources_track_weekly_sources_only():
    assert "DSIT" not in SOURCES
    assert SOURCES["BIST"].endswith("/department-for-business-innovation-science-and-trade")
    assert SOURCES["DCMS"].endswith("/department-for-culture-media-and-sport")
    assert len(WEEKLY_AGENCIES) == 13


def test_zero_without_candidates_is_valid_but_unparsed_candidates_fail():
    healthy = SourceHealth("ICO", True, True, 0, 1)
    assert inspect_results(results(health=[healthy]), results(), SINCE, UNTIL)["ok"]
    anomaly = replace(healthy, candidate_count=2)
    report = inspect_results(results(health=[anomaly]), results(), SINCE, UNTIL)
    assert report["issues"][0]["kind"] == "parser_empty"
    assert not inspect_results(results(), results(), SINCE, UNTIL)["ok"]


def test_production_agency_parser_replay_and_attribution(monkeypatch):
    agency = WEEKLY_AGENCIES[0]
    agency = replace(agency, official_pages=(), news_pages=())
    xml = """<rss><channel><item><title>AI policy</title>
    <link>https://www.gov.uk/government/news/ai-policy</link>
    <pubDate>Mon, 08 Jun 2026 09:00:00 GMT</pubDate></item></channel></rss>"""
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feedparser.parse(xml))
    scraper = AgencyFeedScraper(agency, UNTIL)
    items = scraper.fetch(SINCE)
    health = SourceHealth(agency.short_name, True, True, len(items), 1, candidate_count=scraper.candidate_count)
    assert items and inspect_results(results(items, [health]), results(), SINCE, UNTIL)["ok"]
    items[0].link = "https://unrelated.example/news/ai-policy"
    assert not inspect_results(results(items, [health]), results(), SINCE, UNTIL)["ok"]
    items[0].link = "https://[invalid"
    assert not inspect_results(results(items, [health]), results(), SINCE, UNTIL)["ok"]
    items[0].link = agency.homepage
    assert not inspect_results(results(items, [health]), results(), SINCE, UNTIL)["ok"]


def test_production_parliament_parser_replay_rejects_wrong_host(monkeypatch):
    xml = Path("tests/fixtures/commons_feed.xml").read_text()
    monkeypatch.setattr(
        "UK_news_scraper.scrapers.parliament.research_briefings.parse_feed", lambda _: feedparser.parse(xml)
    )
    items = _fetch_rss("House of Commons Library", SOURCES["UK Parliament"], SINCE)
    health = SourceHealth("Commons", True, True, len(items), 1)
    assert inspect_results(results(), results(items, [health]), SINCE, UNTIL)["ok"]
    items[0].webpage_url = "https://[invalid"
    assert not inspect_results(results(), results(items, [health]), SINCE, UNTIL)["ok"]
    items[0].webpage_url = "https://parliament.uk.attacker.example/item"
    assert not inspect_results(results(), results(items, [health]), SINCE, UNTIL)["ok"]


def test_one_failure_does_not_hide_successful_sources():
    health = [SourceHealth("ICO", True, True, 2, 1), SourceHealth("CMA", True, False, 0, 1, warning="timeout")]
    report = inspect_results(results(health=health), results(), SINCE, UNTIL)
    assert not report["ok"]
    assert len(report["source_health"]) == 2
    assert report["issues"] == [dict(source="CMA", kind="fetch_failed", message="timeout")]
