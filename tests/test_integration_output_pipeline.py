import json
from datetime import date, datetime, timezone

from openpyxl import load_workbook

from UK_news_scraper import excel_exporter
from UK_news_scraper.models import NewsItem, RunStatus
from UK_news_scraper.run_summary import RunSummary, make_data_fingerprint, make_delivery_id, validate_run_summary_payload, write_run_summary


def test_domain_item_to_excel_and_validated_run_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(excel_exporter, "_translate_titles", lambda items: {})
    monkeypatch.setattr(excel_exporter, "_translate_texts", lambda texts, content_label: {})
    item = NewsItem(
        agency="測試機關 (TEST)",
        agency_en="Test Agency",
        unit_category="TEST",
        title="Integration title",
        link="https://example.com/news",
        published_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )
    output = excel_exporter.export_news([item], [], tmp_path / "report.xlsx")
    fingerprint = make_data_fingerprint([item], [])
    run_id = "uk-news-2026-06-12_2026-06-12"
    summary_path = write_run_summary(
        RunSummary(
            run_id=run_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period_start=date(2026, 6, 12).isoformat(),
            period_end=date(2026, 6, 12).isoformat(),
            output_file=str(output),
            all_news_count=1,
            filtered_news_count=0,
            parliament_count=0,
            filtered_parliament_count=0,
            status=RunStatus.COMPLETE,
            warnings=(),
            data_fingerprint=fingerprint,
            delivery_id=make_delivery_id(run_id, RunStatus.COMPLETE, fingerprint),
            source_health=(),
        ),
        output,
    )

    workbook = load_workbook(output, data_only=False)
    payload = validate_run_summary_payload(json.loads(summary_path.read_text(encoding="utf-8")))

    assert workbook["全部新聞"]["E2"].value == "Integration title"
    assert workbook["全部新聞"]["F2"].hyperlink.target == "https://example.com/news"
    assert payload["status"] == "complete"

