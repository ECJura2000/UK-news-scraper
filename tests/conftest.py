import pytest

from UK_news_scraper import standard_time


@pytest.fixture(autouse=True)
def isolate_application_clock(monkeypatch):
    """Unit tests never query public NTP servers or inherit another test's calibration."""
    monkeypatch.setenv("UK_NEWS_TIME_SYNC", "off")
    monkeypatch.setattr(standard_time, "_anchor", None)
    monkeypatch.setattr(standard_time, "_status", standard_time.TimeSync())
    monkeypatch.setattr(standard_time, "_last_attempt", -float("inf"))
