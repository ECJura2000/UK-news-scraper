from datetime import datetime, timezone

from openpyxl import load_workbook

from UK_news_scraper.excel_exporter import export_news
from UK_news_scraper.models import NewsItem, ParliamentBriefing


def test_export_contains_required_sheets_and_preserves_distinct_links(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "UK_news_scraper.excel_exporter._translate_texts",
        lambda texts, content_label: {},
    )
    items = [
        NewsItem("Agency", "Agency", "A", "Same title", link, datetime(2026, 6, 8, tzinfo=timezone.utc))
        for link in ("https://example.com/a", "https://example.com/b")
    ]
    parliament = [
        ParliamentBriefing(
            published_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
            chamber="House of Commons",
            publisher="House of Commons Library",
            title="Research title",
            summary="Summary",
            identifier="CBP-1",
            webpage_url="https://example.com/research",
        )
    ]

    path = export_news(items, [], tmp_path / "report.xlsx", parliament_items=parliament)
    workbook = load_workbook(path, read_only=True, data_only=True)

    assert workbook.sheetnames == ["全部新聞", "已初步篩選工作表", "國會研究資料"]
    assert workbook["全部新聞"].max_row == 5
