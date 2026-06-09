import json

from UK_news_scraper.http.async_client import get_session
from UK_news_scraper.translation_cache import load_translations, save_translations


def test_http_session_is_reused_in_same_thread():
    assert get_session() is get_session()


def test_translation_cache_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "translations.json"
    monkeypatch.setenv("UK_NEWS_TRANSLATION_CACHE", str(path))

    save_translations({"Hello": "哈囉"})

    assert load_translations() == {"Hello": "哈囉"}
    assert json.loads(path.read_text(encoding="utf-8"))["Hello"] == "哈囉"
