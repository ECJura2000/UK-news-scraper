"""Official Parliament feeds, API, and topic archives stay independently healthy."""

from datetime import UTC, datetime
from types import SimpleNamespace

from UK_news_scraper.models import ParliamentBriefing
from UK_news_scraper.scrapers.parliament import research_briefings as parliament

SINCE = datetime(2026, 9, 14, tzinfo=UTC)


def _briefing(source="House of Commons Library"):
    return ParliamentBriefing(
        published_at=datetime(2026, 9, 20, tzinfo=UTC),
        chamber="House of Commons",
        publisher=source,
        title="UK online safety research briefing",
        summary="Digital policy",
        identifier="CBP-1234",
        webpage_url="https://commonslibrary.parliament.uk/research-briefings/cbp-1234/",
    )


def test_api_pagination_normalizes_official_record_and_stops_on_old_page(monkeypatch):
    pages = [
        {
            "result": {
                "items": [
                    {
                        "publisher": {"prefLabel": "House of Commons Library"},
                        "date": "2026-09-20",
                        "title": "Online safety",
                        "_about": {"_value": "https://example.org/CBP-1234"},
                        "topic": [{"_value": "Technology"}],
                        "identifier": "CBP-1234",
                    },
                    {
                        "publisher": "House of Lords Library",
                        "date": "2026-09-01",
                        "title": "Older law",
                        "_about": "https://example.org/LLN-1234",
                    },
                ]
            }
        },
    ]
    monkeypatch.setattr(parliament, "get_json", lambda _url, **_kwargs: pages.pop(0))
    records = parliament._fetch_api(SINCE, page_size=2, max_pages=3)
    assert len(records) == 1
    assert records[0].identifier == "CBP-1234"
    assert records[0].topics == ["Technology"]
    assert records[0].chamber == "House of Commons"


def test_rss_and_topic_archive_extract_official_links_without_network(monkeypatch):
    entry = SimpleNamespace(
        published="2026-09-20T00:00:00Z",
        title="Commons research briefing CBP-1234",
        link="https://commonslibrary.parliament.uk/research-briefings/cbp-1234/",
        id="CBP-1234",
        summary="Online safety briefing",
        content=[
            {"value": "<a href='https://researchbriefings.files.parliament.uk/documents/CBP-1234/CBP-1234.pdf'>PDF</a>"}
        ],
        tags=[{"term": "Technology"}],
    )
    monkeypatch.setattr(parliament, "parse_feed", lambda _url: SimpleNamespace(entries=[entry]))
    records = parliament._fetch_rss("House of Commons Library", "https://official.example/feed", SINCE)
    assert records[0].identifier == "CBP-1234"
    assert records[0].pdf_url.endswith("CBP-1234.pdf")
    assert records[0].topics == ["Technology"]

    page = """<article class="card">
      <h2 class="card__heading"><a href="/research-briefings/cbp-5678/">New technologies CBP-5678</a></h2>
      <time datetime="2026-09-20T00:00:00+00:00"></time>
      <div class="tag-list"><a href="/topic/technology/">Technology</a><a href="/type/briefing/">Briefing</a></div>
    </article>"""
    monkeypatch.setattr(parliament, "get_text", lambda _url: page)
    archive = parliament._fetch_topic_archive(
        SINCE,
        "https://official.example/topic/technology/",
        "House of Commons",
        "House of Commons Library",
        max_pages=1,
    )
    assert archive[0].document_type == "Briefing"
    assert archive[0].webpage_url == "https://official.example/research-briefings/cbp-5678/"


def test_api_failure_keeps_rss_data_and_records_source_health(monkeypatch):
    monkeypatch.setenv("UK_PARLIAMENT_TRY_API", "1")
    monkeypatch.setattr(parliament, "_fetch_api", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(parliament, "_fetch_rss", lambda publisher, *_args: [_briefing(publisher)])
    monkeypatch.setattr(parliament, "_fetch_topic_archive", lambda *_args, **_kwargs: [])
    result = parliament.fetch_parliament_briefings(SINCE)
    assert result.items
    assert result.source_mode.startswith("Official RSS")
    assert any("API" in warning for warning in result.warnings)
    assert any(health.source == "Research Briefings API" and not health.success for health in result.source_health)


def test_topic_archive_failure_isolated_from_successful_api(monkeypatch):
    monkeypatch.setenv("UK_PARLIAMENT_TRY_API", "1")
    monkeypatch.setattr(parliament, "_fetch_api", lambda *_args, **_kwargs: [_briefing()])

    def archive(_since, *, archive_url, **_kwargs):
        if "technology" in archive_url and "lordslibrary" in archive_url:
            raise OSError("archive unavailable")
        return []

    monkeypatch.setattr(parliament, "_fetch_topic_archive", archive)
    result = parliament.fetch_parliament_briefings(SINCE)
    assert result.items[0].identifier == "CBP-1234"
    assert any("topic archive" in source for source in result.failed_sources)
    assert result.all_successful
