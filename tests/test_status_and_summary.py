import json
from datetime import date, datetime, timezone

from UK_news_scraper.main import _run_status
from UK_news_scraper.run_summary import RunSummary, make_run_id, write_run_summary
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
    start = datetime(2026, 5, 24, 16, tzinfo=timezone.utc)
    end = datetime(2026, 6, 8, 16, tzinfo=timezone.utc)
    output = tmp_path / "report.xlsx"
    summary = RunSummary(
        run_id=make_run_id(date(2026, 5, 25), date(2026, 6, 8)),
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
    )

    path = write_run_summary(summary, output)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "uk-news-2026-05-25_2026-06-08"
    assert payload["status"] == "complete"
