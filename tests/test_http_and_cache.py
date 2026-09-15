import json
import asyncio
from types import SimpleNamespace

from UK_news_scraper.excel_exporter import _translate_titles_async
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


def test_googletrans_translation_uses_bounded_concurrency(monkeypatch):
    active = 0
    maximum_active = 0

    class FakeTranslator:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def translate(self, text, **_):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return SimpleNamespace(text=f"中譯 {text}")

    monkeypatch.setenv("UK_NEWS_TRANSLATION_CONCURRENCY", "3")
    translated = asyncio.run(
        _translate_titles_async(
            ["one", "two", "three", "four", "five"],
            FakeTranslator,
            "test",
        )
    )

    assert len(translated) == 5
    assert 1 < maximum_active <= 3
