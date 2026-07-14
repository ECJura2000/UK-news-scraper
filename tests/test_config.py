from pathlib import Path

from UK_news_scraper.config import _default_output_dir


def test_output_directory_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("UK_NEWS_OUTPUT_DIR", str(tmp_path))

    assert _default_output_dir() == Path(tmp_path)


def test_source_checkout_defaults_to_project_output_directory(monkeypatch):
    monkeypatch.delenv("UK_NEWS_OUTPUT_DIR", raising=False)

    assert _default_output_dir().name == "新聞放置區"
