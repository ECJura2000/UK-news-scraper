from datetime import date, datetime, timezone

from UK_news_scraper.app_service import (
    ExportOptionsRequest,
    RunRequest,
    execute_run,
)
from UK_news_scraper.calendar_utils import CalendarMode
from UK_news_scraper.models import NewsItem
from UK_news_scraper.profiles import (
    FilterProfile,
    KeywordDefinition,
    KeywordStrength,
    ProfileTopic,
)
from UK_news_scraper.scrapers.ministry.status import AgencyFetchStatus, FetchAllResult


def test_application_service_writes_custom_filename_and_summary(monkeypatch, tmp_path):
    item = NewsItem(
        "科學、創新和技術部 (DSIT)",
        "Department for Science, Innovation and Technology",
        "DSIT",
        "Digital health framework announced",
        "https://example.com/news",
        datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    profile = FilterProfile(
        profile_id="digital-health",
        name="數位健康",
        description="",
        version=1,
        selected_sources=("DSIT",),
        topics=(
            ProfileTopic(
                "數位健康",
                (KeywordDefinition("digital health", KeywordStrength.CORE),),
            ),
        ),
        minimum_score=3,
    )
    fetch_result = FetchAllResult(
        items=[item],
        statuses=[
            AgencyFetchStatus(
                agency_name="DSIT",
                source_name="DSIT",
                success=True,
                item_count=1,
            )
        ],
    )
    monkeypatch.setattr(
        "UK_news_scraper.app_service.fetch_all_with_status",
        lambda since, max_workers, agencies: fetch_result,
    )

    def fake_export(all_items, filtered_items, output, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"xlsx")
        return output

    monkeypatch.setattr("UK_news_scraper.app_service.export_news", fake_export)
    events = []

    result = execute_run(
        RunRequest(
            period_start=date(2026, 7, 13),
            period_end=date(2026, 7, 27),
            output_dir=tmp_path,
            profile=profile,
            export_options=ExportOptionsRequest(calendar_mode=CalendarMode.ROC),
        ),
        progress=events.append,
    )

    assert result.workbook_path.name == "20260713-20260727_UK新聞查詢_digital-health.xlsx"
    assert result.summary.profile_id == "digital-health"
    assert result.summary.excel_date_calendar == "roc"
    assert result.summary.filtered_news_count == 1
    assert result.summary_path.exists()
    assert [event.stage for event in events] == ["fetch_news", "filter_news", "export", "done"]
