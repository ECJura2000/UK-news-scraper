import json
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

import pytest

from UK_news_scraper.config import AGENCIES
from UK_news_scraper.errors import DownloadError
from UK_news_scraper.models import Agency
from UK_news_scraper.profiles import default_profile, validate_profile
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper
from UK_news_scraper.source_catalog import catalog_entries


def test_official_catalog_is_opt_in_and_covers_devolved_bodies_and_courts():
    entries = catalog_entries()
    ids = {entry["id"] for entry in entries}
    assert len(ids) == len(entries)
    assert {"UK", "Scotland", "Wales", "Northern Ireland", "England and Wales"} <= {
        entry["jurisdiction"] for entry in entries
    }
    removed_id = "court-ew:administrative-divisional-court"
    assert removed_id not in ids
    state = json.loads(files("UK_news_scraper").joinpath("data/source_catalog_overrides.json").read_text())
    removed = next(item for item in state["exclusions"] if item["id"] == removed_id)
    assert removed["original_source"]["id"] == removed_id
    available = ids | {agency.short_name for agency in AGENCIES}
    assert removed["replacement_sources"] and set(removed["replacement_sources"]) <= available
    assert any(entry["id"] == "court-scotland:judgments" and entry["status"] == "searchable" for entry in entries)
    assert "govuk:bbc" not in {agency.short_name for agency in AGENCIES}
    assert all(
        not source.startswith(("govuk:", "court-", "ni:", "wales:", "scotland:"))
        for source in default_profile().selected_sources
    )


def test_json_profile_accepts_live_catalog_source_but_rejects_directory_only():
    profile = default_profile()
    live = next(agency.short_name for agency in AGENCIES if agency.short_name.startswith("govuk:"))
    validate_profile(replace(profile, selected_sources=(live, "court-ew:judgments")))
    with pytest.raises(ValueError, match="未知來源"):
        validate_profile(replace(profile, selected_sources=("court-ew:administrative-divisional-court",)))


def test_govuk_decisions_use_bounded_search_and_keep_partial_pages(monkeypatch):
    agency = next(
        agency for agency in AGENCIES if agency.short_name == "govuk:upper-tribunal-administrative-appeals-chamber"
    )
    scraper = AgencyFeedScraper(agency, datetime(2026, 9, 24, tzinfo=UTC))
    seen = []

    def fake_search(url):
        seen.append(parse_qs(urlparse(url).query))
        if len(seen) == 2:
            raise OSError("second page unavailable")
        return {
            "total": 2,
            "results": [
                {
                    "title": "Tribunal decision on digital evidence",
                    "link": "/administrative-appeals-tribunal-decisions/test-decision",
                    "public_timestamp": "2026-09-23T10:00:00Z",
                    "description": "Decision summary",
                    "format": "utaac_decision",
                }
            ],
        }

    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_json", fake_search)
    items = scraper.fetch(datetime(2026, 9, 23, tzinfo=UTC))
    assert len(items) == 1
    assert items[0].content_type == "judgment"
    assert seen[0]["filter_public_timestamp"] == ["from:2026-09-23,to:2026-09-24"]
    assert scraper.source_warnings and "已保留" in scraper.source_warnings[0]


def test_govuk_search_rejects_unusable_first_page(monkeypatch):
    agency = Agency("官方機關", "Official", "govuk:test", "https://www.gov.uk/government/organisations/test")
    scraper = AgencyFeedScraper(agency)
    monkeypatch.setattr(
        "UK_news_scraper.scrapers.ministry.registry.get_json",
        lambda _url: (_ for _ in ()).throw(OSError("offline")),
    )
    with pytest.raises(DownloadError, match="搜尋失敗"):
        scraper.fetch(datetime(2026, 9, 23, tzinfo=UTC))
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_json", lambda _url: {"results": None})
    with pytest.raises(DownloadError, match="格式錯誤"):
        scraper.fetch(datetime(2026, 9, 23, tzinfo=UTC))


def test_govuk_search_reports_invalid_records_without_dropping_valid_ones(monkeypatch):
    agency = Agency(
        "官方機關",
        "Official",
        "govuk:test",
        "https://www.gov.uk/government/organisations/test",
        link_include_patterns=("/government/news/",),
    )
    scraper = AgencyFeedScraper(agency, datetime(2026, 9, 24, tzinfo=UTC))
    records = [
        {"title": "No link"},
        {"link": "/government/news/no-date", "title": "No date"},
        {"link": "/government/news/bad-date", "public_timestamp": "invalid", "title": "Bad date"},
        {"link": "/government/news/old", "public_timestamp": "2026-09-01T10:00:00Z", "title": "Old"},
        {"link": "/government/news/future", "public_timestamp": "2026-09-24T10:00:00Z", "title": "Future"},
        {"link": "/government/news/no-title", "public_timestamp": "2026-09-23T10:00:00Z"},
        {
            "link": "/government/news/valid",
            "public_timestamp": "2026-09-23T10:00:00Z",
            "title": "Valid digital policy update",
            "description": "Official policy",
        },
    ]
    monkeypatch.setattr(
        "UK_news_scraper.scrapers.ministry.registry.get_json",
        lambda _url: {"results": records, "total": len(records)},
    )
    items = scraper.fetch(datetime(2026, 9, 23, tzinfo=UTC))
    assert [item.title for item in items] == ["Valid digital policy update"]
    assert scraper.candidate_count == 2
    assert len(scraper.source_warnings) == 4


def test_govuk_search_preserves_first_page_after_malformed_second_page(monkeypatch):
    agency = Agency(
        "官方機關",
        "Official",
        "govuk:test",
        "https://www.gov.uk/government/organisations/test",
        link_include_patterns=("/government/news/",),
    )
    scraper = AgencyFeedScraper(agency)
    pages = iter(
        [
            {
                "results": [
                    {
                        "link": "/government/news/valid",
                        "title": "Valid digital policy update",
                        "public_timestamp": "2026-09-23T10:00:00Z",
                    }
                ],
                "total": 2,
            },
            {"results": None},
        ]
    )
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_json", lambda _url: next(pages))
    items = scraper.fetch(datetime(2026, 9, 23, tzinfo=UTC))
    assert len(items) == 1
    assert any("格式異常" in warning for warning in scraper.source_warnings)
