from datetime import datetime, timezone
import json

import pytest

from UK_news_scraper.excel_exporter import export_news
from UK_news_scraper.logging_utils import log_event
from UK_news_scraper.models import NewsItem


def test_failed_excel_verification_preserves_existing_file(tmp_path, monkeypatch):
    output = tmp_path / "report.xlsx"
    output.write_bytes(b"existing")
    monkeypatch.setattr("UK_news_scraper.excel_exporter._translate_texts", lambda texts, content_label: {})
    monkeypatch.setattr(
        "UK_news_scraper.excel_exporter.load_workbook",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("verification failed")),
    )
    item = NewsItem("Agency", "Agency", "A", "Title", "https://example.com", datetime(2026, 6, 8, tzinfo=timezone.utc))

    with pytest.raises(RuntimeError, match="verification failed"):
        export_news([item], [], output)

    assert output.read_bytes() == b"existing"


def test_structured_logging(monkeypatch, capsys):
    monkeypatch.setenv("UK_NEWS_LOG_FORMAT", "json")

    log_event("done", "test_event", "message", count=3)

    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "test_event"
    assert payload["count"] == 3
