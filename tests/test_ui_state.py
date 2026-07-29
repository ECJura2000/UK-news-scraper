from datetime import date, datetime, timezone
import json

from UK_news_scraper.models import NewsItem, SourceHealth
from UK_news_scraper.ui_components import HIGHLIGHT_PRIORITY, configure_relevance_tags
from UK_news_scraper.ui_state import (
    ResultFilters,
    failed_source_ids,
    filter_and_sort_results,
    load_run_history,
)


def _item(
    title: str,
    *,
    score: int,
    published: date,
    agency: str = "DSIT",
    topics: list[str] | None = None,
    core: list[str] | None = None,
) -> NewsItem:
    return NewsItem(
        agency=agency,
        agency_en=agency,
        unit_category=None,
        title=title,
        link=f"https://example.com/{title}",
        published_at=datetime.combine(
            published,
            datetime.min.time(),
            tzinfo=timezone.utc,
        ),
        summary="Policy summary",
        matched_topics=topics or [],
        matched_keywords=core or [],
        core_matched_keywords=core or [],
        relevance_score=score,
        relevance_level="高" if score >= 8 else "中",
    )


def test_result_filters_cover_score_date_topic_and_sorting():
    rows = [
        ("新聞", _item("Older", score=8, published=date(2026, 7, 1), topics=["AI"], core=["AI"])),
        ("新聞", _item("Target", score=6, published=date(2026, 7, 20), topics=["AI"], core=["AI"])),
        ("新聞", _item("Low", score=2, published=date(2026, 7, 21), topics=["Data"])),
    ]

    filtered = filter_and_sort_results(
        rows,
        ResultFilters(
            query="target",
            topic="AI",
            strength="核心",
            minimum_score=5,
            maximum_score=7,
            date_start=date(2026, 7, 10),
            date_end=date(2026, 7, 31),
        ),
        sort_column="date",
    )

    assert [item.title for _item_type, item in filtered] == ["Target"]


def test_failed_sources_map_parliament_health_to_profile_source():
    health = [
        SourceHealth("DSIT", True, False, 0, 1.0, warning="failed"),
        SourceHealth("Commons Library RSS", True, True, 0, 1.0, warning="empty"),
        SourceHealth("ICO", True, True, 2, 1.0),
    ]

    assert failed_source_ids(health) == ("DSIT", "UK Parliament")


def test_history_ignores_invalid_summaries_and_orders_newest_first(tmp_path):
    workbook = tmp_path / "report.xlsx"
    workbook.touch()
    valid = {
        "delivery_id": "delivery",
        "run_id": "run",
        "status": "complete",
        "data_fingerprint": "fingerprint",
        "output_file": str(workbook),
        "generated_at": "2026-07-28T12:00:00+00:00",
        "period_start": "2026-07-14",
        "period_end": "2026-07-28",
        "profile_name": "UK 科技法制",
        "all_news_count": 24,
        "filtered_news_count": 10,
        "parliament_count": 131,
    }
    (tmp_path / "valid.run.json").write_text(json.dumps(valid), encoding="utf-8")
    (tmp_path / "invalid.run.json").write_text("{", encoding="utf-8")

    entries = load_run_history(tmp_path)

    assert len(entries) == 1
    assert entries[0].workbook_path == workbook
    assert entries[0].filtered_news_count == 10


def test_highlight_priority_always_raises_core_last():
    calls = []

    class FakeText:
        def tag_configure(self, tag, **kwargs):
            calls.append(("configure", tag, kwargs["background"]))

        def tag_raise(self, tag):
            calls.append(("raise", tag))

    configure_relevance_tags(FakeText())

    raises = [call[1] for call in calls if call[0] == "raise"]
    assert raises == list(HIGHLIGHT_PRIORITY)
    assert raises[-1] == "core"
