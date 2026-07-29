from datetime import date, datetime, timezone

from UK_news_scraper.app_service import (
    ExportOptionsRequest,
    RunCancelled,
    RunRequest,
    RunResult,
    execute_run,
)
from UK_news_scraper.calendar_utils import CalendarMode
from UK_news_scraper.models import NewsItem, RunStatus, SourceHealth
from UK_news_scraper.profiles import (
    FilterProfile,
    KeywordDefinition,
    KeywordStrength,
    ProfileTopic,
)
from UK_news_scraper.scrapers.ministry.status import AgencyFetchStatus, FetchAllResult
from UK_news_scraper.run_summary import RunSummary


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


def test_application_service_can_cancel_before_fetch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "UK_news_scraper.app_service.fetch_all_with_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fetch should not run")),
    )

    try:
        execute_run(
            RunRequest(
                period_start=date(2026, 7, 13),
                period_end=date(2026, 7, 27),
                output_dir=tmp_path,
            ),
            cancelled=lambda: True,
        )
    except RunCancelled:
        pass
    else:
        raise AssertionError("cancelled run should raise RunCancelled")


def test_retry_preserves_successful_sources_and_replaces_failed_source(monkeypatch, tmp_path):
    old_dsit = NewsItem(
        "科學、創新和技術部 (DSIT)",
        "Department for Science, Innovation and Technology",
        "DSIT",
        "Old DSIT item",
        "https://example.com/old-dsit",
        datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    ico = NewsItem(
        "英國資訊專員辦公室 (ICO)",
        "Information Commissioner's Office",
        "ICO",
        "ICO item",
        "https://example.com/ico",
        datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    new_dsit = NewsItem(
        old_dsit.agency,
        old_dsit.agency_en,
        old_dsit.unit_category,
        "New DSIT item",
        "https://example.com/new-dsit",
        datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    profile = FilterProfile(
        profile_id="retry-test",
        name="Retry",
        description="",
        version=1,
        selected_sources=("DSIT", "ICO"),
        topics=(
            ProfileTopic(
                "Policy",
                (KeywordDefinition("item", KeywordStrength.CORE),),
            ),
        ),
        minimum_score=1,
    )
    base_summary = RunSummary(
        run_id="run",
        generated_at="2026-07-27T00:00:00+00:00",
        period_start="2026-07-13",
        period_end="2026-07-27",
        output_file=str(tmp_path / "base.xlsx"),
        all_news_count=2,
        filtered_news_count=2,
        parliament_count=0,
        filtered_parliament_count=0,
        status=RunStatus.DEGRADED,
        warnings=("DSIT failed",),
        data_fingerprint="fingerprint",
        delivery_id="delivery",
        source_health=(
            SourceHealth("DSIT", True, False, 0, 1.0, warning="failed"),
            SourceHealth("ICO", True, True, 1, 1.0),
        ),
        profile_id=profile.profile_id,
        profile_name=profile.name,
        selected_sources=profile.selected_sources,
    )
    base = RunResult(
        workbook_path=tmp_path / "base.xlsx",
        summary_path=tmp_path / "base.run.json",
        summary=base_summary,
        all_items=(old_dsit, ico),
        filtered_items=(old_dsit, ico),
        parliament_items=(),
        filtered_parliament_items=(),
    )
    monkeypatch.setattr(
        "UK_news_scraper.app_service.fetch_all_with_status",
        lambda since, max_workers, agencies: FetchAllResult(
            items=[new_dsit],
            statuses=[
                AgencyFetchStatus(
                    agency_name="DSIT",
                    source_name="DSIT",
                    success=True,
                    item_count=1,
                )
            ],
        ),
    )

    def fake_export(all_items, filtered_items, output, **kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"xlsx")
        return output

    monkeypatch.setattr("UK_news_scraper.app_service.export_news", fake_export)

    result = execute_run(
        RunRequest(
            period_start=date(2026, 7, 13),
            period_end=date(2026, 7, 27),
            output_dir=tmp_path,
            profile=profile,
            retry_source_ids=("DSIT",),
            base_result=base,
        )
    )

    assert {item.title for item in result.all_items} == {"New DSIT item", "ICO item"}
    assert result.summary.status == RunStatus.COMPLETE
    assert [health.source for health in result.summary.source_health] == ["DSIT", "ICO"]
