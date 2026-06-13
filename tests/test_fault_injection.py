from datetime import datetime, timezone

from UK_news_scraper.errors import DownloadError, ParseError
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry import orchestration


class FakeScraper:
    def __init__(self, error):
        self.error = error
        self.calls = 0
        self.agency = Agency("測試", "Test", "TEST", "https://example.test")

    def fetch(self, since):
        self.calls += 1
        raise self.error


def test_only_download_failure_is_retried(monkeypatch):
    download = FakeScraper(DownloadError("temporary"))
    parse = FakeScraper(ParseError("bad payload"))
    monkeypatch.setattr(orchestration, "build_scrapers", lambda: [download, parse])
    monkeypatch.setattr(orchestration, "sleep", lambda _: None)

    result = orchestration.fetch_all_with_status(datetime.now(timezone.utc), max_workers=2)

    assert download.calls == 2
    assert parse.calls == 1
    assert len(result.failed_statuses) == 2

