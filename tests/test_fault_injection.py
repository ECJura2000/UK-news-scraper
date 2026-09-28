from datetime import UTC, datetime
from time import monotonic

from UK_news_scraper.errors import DownloadError, ParseError
from UK_news_scraper.models import Agency, NewsItem
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

    result = orchestration.fetch_all_with_status(datetime.now(UTC), max_workers=2)

    assert download.calls == 2
    assert parse.calls == 1
    assert len(result.failed_statuses) == 2


def test_retry_success_keeps_in_period_records_without_waiting_past_deadline(monkeypatch):
    since = datetime(2026, 9, 23, tzinfo=UTC)
    until = datetime(2026, 9, 24, tzinfo=UTC)

    class RecoveringScraper:
        agency = Agency("測試", "Test", "TEST", "https://example.test")
        source_warnings = []
        candidate_count = 2
        calls = 0

        def fetch(self, _since):
            self.calls += 1
            if self.calls == 1:
                raise DownloadError("temporary")
            return [
                NewsItem("測試", "Test", "TEST", "Valid digital policy update", "https://example.test/one", since),
                NewsItem("測試", "Test", "TEST", "Out-of-period update", "https://example.test/two", until),
            ]

    scraper = RecoveringScraper()
    monkeypatch.setattr(orchestration, "build_scrapers", lambda *_args, **_kwargs: [scraper])
    monkeypatch.setattr(orchestration, "sleep", lambda _seconds: (_ for _ in ()).throw(AssertionError("late sleep")))
    result = orchestration.fetch_all_with_status(since, agencies=(scraper.agency,), until=until, deadline=monotonic())
    assert scraper.calls == 2
    assert [item.link for item in result.items] == ["https://example.test/one"]
    assert result.statuses[0].attempts == 2


def test_empty_selection_returns_without_starting_workers(monkeypatch):
    monkeypatch.setattr(orchestration, "build_scrapers", lambda *_args, **_kwargs: [])
    result = orchestration.fetch_all_with_status(datetime(2026, 9, 23, tzinfo=UTC))
    assert result.items == []
    assert result.statuses == []
