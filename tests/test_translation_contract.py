"""Translation timeout and provider failures preserve the English report text."""

import asyncio
from types import SimpleNamespace

from UK_news_scraper import translation_service


def test_async_translation_uses_bounded_requests_and_english_fallback():
    class Translator:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def translate(self, title, **_kwargs):
            if title == "service unavailable":
                raise OSError("offline")
            return SimpleNamespace(text="人工智慧政策")

    translations = asyncio.run(
        translation_service.translate_titles_async(
            ["AI policy", "service unavailable"],
            Translator,
            "標題",
            concurrency=2,
            request_timeout=0.1,
            budget=0.3,
        )
    )
    assert translations == {"AI policy": "人工智慧政策", "service unavailable": ""}


def test_zero_translation_budget_returns_without_waiting_for_provider():
    class Translator:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def translate(self, *_args, **_kwargs):
            raise AssertionError("budget should stop the provider call")

    translated = asyncio.run(
        translation_service.translate_titles_async(
            ["English title"], Translator, "標題", concurrency=1, request_timeout=1, budget=0
        )
    )
    assert translated == {"English title": ""}


def test_manual_election_titles_and_deep_translator_fallback(monkeypatch):
    assert (
        translation_service._translate_election_statement_title(
            "Post count statement - 2026 Scottish Parliament election"
        )
        == "計票後聲明 - 2026 年蘇格蘭議會選舉"
    )
    assert (
        translation_service._translate_election_statement_title("Post poll statement - September 2026")
        == "投票後聲明 - 2026 年 9 月"
    )

    from deep_translator import GoogleTranslator

    monkeypatch.setattr(
        GoogleTranslator, "translate", lambda _self, title: "中文標題" if title == "Policy title" else title
    )
    assert translation_service._translate_with_deep_translator("Policy title") == "中文標題"
    assert translation_service._translate_with_deep_translator("Unchanged") == ""
    assert translation_service._translate_titles_with_deep_translator(["Policy title"])["Policy title"] == "中文標題"
