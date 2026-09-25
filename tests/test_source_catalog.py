from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from UK_news_scraper.config import AGENCIES
from UK_news_scraper.profiles import default_profile, validate_profile
from UK_news_scraper.source_catalog import catalog_entries
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper


def test_official_catalog_is_opt_in_and_covers_devolved_bodies_and_courts():
    entries = catalog_entries()
    ids = {entry["id"] for entry in entries}
    assert len(ids) == len(entries)
    assert {"UK", "Scotland", "Wales", "Northern Ireland", "England and Wales"} <= {
        entry["jurisdiction"] for entry in entries
    }
    assert any(entry["id"] == "court-ew:administrative-divisional-court" for entry in entries)
    assert any(entry["id"] == "court-scotland:judgments" and entry["status"] == "searchable" for entry in entries)
    assert "govuk:bbc" not in {agency.short_name for agency in AGENCIES}
    assert all(not source.startswith(("govuk:", "court-", "ni:", "wales:", "scotland:")) for source in default_profile().selected_sources)


def test_json_profile_accepts_live_catalog_source_but_rejects_directory_only():
    profile = default_profile()
    live = next(agency.short_name for agency in AGENCIES if agency.short_name.startswith("govuk:"))
    validate_profile(replace(profile, selected_sources=(live, "court-ew:judgments")))
    with pytest.raises(ValueError, match="未知來源"):
        validate_profile(replace(profile, selected_sources=("court-ew:administrative-divisional-court",)))


def test_govuk_decisions_use_bounded_search_and_keep_partial_pages(monkeypatch):
    agency = next(agency for agency in AGENCIES if agency.short_name == "govuk:upper-tribunal-administrative-appeals-chamber")
    scraper = AgencyFeedScraper(agency, datetime(2026, 9, 24, tzinfo=timezone.utc))
    seen = []

    def fake_search(url):
        seen.append(parse_qs(urlparse(url).query))
        if len(seen) == 2:
            raise OSError("second page unavailable")
        return {"total": 2, "results": [{
            "title": "Tribunal decision on digital evidence",
            "link": "/administrative-appeals-tribunal-decisions/test-decision",
            "public_timestamp": "2026-09-23T10:00:00Z",
            "description": "Decision summary",
            "format": "utaac_decision",
        }]}

    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_json", fake_search)
    items = scraper.fetch(datetime(2026, 9, 23, tzinfo=timezone.utc))
    assert len(items) == 1
    assert items[0].content_type == "judgment"
    assert seen[0]["filter_public_timestamp"] == ["from:2026-09-23,to:2026-09-24"]
    assert scraper.source_warnings and "已保留" in scraper.source_warnings[0]
