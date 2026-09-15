from pathlib import Path

from UK_news_scraper.config import AGENCIES, SOURCE_HEALTH_MAX_AGE_DAYS, _default_output_dir


def test_output_directory_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("UK_NEWS_OUTPUT_DIR", str(tmp_path))

    assert _default_output_dir() == Path(tmp_path)


def test_source_checkout_defaults_to_project_output_directory(monkeypatch):
    monkeypatch.delenv("UK_NEWS_OUTPUT_DIR", raising=False)

    assert _default_output_dir().name == "新聞放置區"


def test_dsit_split_successors_replace_legacy_departments():
    agencies = {agency.short_name: agency for agency in AGENCIES}

    assert "DSIT" not in agencies
    assert "DBT" not in agencies
    assert agencies["BIST"].topics == (
        "Science & Technology",
        "AI",
        "半導體/量子技術",
    )
    assert agencies["DCMS"].topics == (
        "資料治理/隱私/數位身份",
        "數位平台",
        "網路安全/資安",
    )
    assert "AI" in agencies["Cabinet Office"].topics
    assert agencies["AISI"].name_en == "AI Security Institute"
    assert SOURCE_HEALTH_MAX_AGE_DAYS["BIST"] == 14
    assert SOURCE_HEALTH_MAX_AGE_DAYS["DCMS"] == 14
