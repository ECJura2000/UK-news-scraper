import json
from datetime import date, datetime, timezone
from pathlib import Path

from UK_news_scraper.main import _run_status
from UK_news_scraper.models import NewsItem, ParliamentBriefing
from UK_news_scraper.run_summary import (
    RunSummary,
    make_data_fingerprint,
    make_delivery_id,
    make_run_id,
    write_run_summary,
)
from UK_news_scraper.scrapers.ministry.registry import AgencyFetchStatus, FetchAllResult
from UK_news_scraper.scrapers.parliament.research_briefings import ParliamentFetchResult


def test_parliament_failure_makes_overall_status_degraded():
    ministry = FetchAllResult(
        items=[],
        statuses=[AgencyFetchStatus(agency_name="Agency", success=True)],
    )
    parliament = ParliamentFetchResult(
        items=[],
        source_mode="RSS",
        warnings=["Commons RSS failed"],
        failed_sources=["Commons RSS"],
    )

    status, warnings = _run_status(ministry, parliament)

    assert status == "degraded"
    assert warnings == ["Commons RSS failed"]


def test_run_summary_is_machine_readable(tmp_path):
    end = datetime(2026, 6, 8, 16, tzinfo=timezone.utc)
    output = tmp_path / "report.xlsx"
    fingerprint = "a" * 64
    run_id = make_run_id(date(2026, 5, 25), date(2026, 6, 8))
    summary = RunSummary(
        run_id=run_id,
        generated_at=end.isoformat(),
        period_start="2026-05-25",
        period_end="2026-06-08",
        output_file=str(output),
        all_news_count=10,
        filtered_news_count=2,
        parliament_count=3,
        filtered_parliament_count=1,
        status="complete",
        warnings=(),
        data_fingerprint=fingerprint,
        delivery_id=make_delivery_id(run_id, "complete", fingerprint),
        source_health=(),
    )

    path = write_run_summary(summary, output)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "uk-news-2026-05-25_2026-06-08"
    assert payload["status"] == "complete"


def test_data_fingerprint_changes_when_visible_summary_changes():
    original = NewsItem(
        agency="Agency",
        agency_en="Agency",
        unit_category="A",
        title="Title",
        link="https://example.com/item",
        published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        summary="Original summary",
    )
    changed = NewsItem(
        agency=original.agency,
        agency_en=original.agency_en,
        unit_category=original.unit_category,
        title=original.title,
        link=original.link,
        published_at=original.published_at,
        summary="Corrected summary",
    )

    assert make_data_fingerprint([original], []) != make_data_fingerprint([changed], [])


def test_data_fingerprint_is_not_ambiguous_when_fields_contain_delimiters():
    first = NewsItem(
        agency="A|B",
        agency_en="C",
        unit_category=None,
        title="Title",
        link="https://example.com",
        published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    second = NewsItem(
        agency="A",
        agency_en="B|C",
        unit_category=None,
        title="Title",
        link="https://example.com",
        published_at=first.published_at,
    )

    assert make_data_fingerprint([first], []) != make_data_fingerprint([second], [])


def test_data_fingerprint_is_independent_of_record_order():
    first = NewsItem(
        agency="A",
        agency_en="A",
        unit_category=None,
        title="First",
        link="https://example.com/first",
        published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    second = NewsItem(
        agency="B",
        agency_en="B",
        unit_category=None,
        title="Second",
        link="https://example.com/second",
        published_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    assert make_data_fingerprint([first, second], []) == make_data_fingerprint([second, first], [])


def test_fingerprint_v3_matches_shared_rust_golden_fixture():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "fingerprint_v3_golden.json").read_text(
            encoding="utf-8"
        )
    )
    news = [
        NewsItem(
            **{
                **item,
                "published_at": datetime.fromisoformat(
                    item["published_at"].replace("Z", "+00:00")
                ),
            }
        )
        for item in fixture["news"]
    ]
    parliament = [
        ParliamentBriefing(
            **{
                **item,
                "published_at": datetime.fromisoformat(
                    item["published_at"].replace("Z", "+00:00")
                ),
            }
        )
        for item in fixture["parliament"]
    ]
    assert make_data_fingerprint(news, parliament) == fixture["expected"]
