from __future__ import annotations

import asyncio
import re
from typing import Any

from .dedupe import normalize_title
from .performance import http_attempt, http_status

MANUAL_TITLE_TRANSLATIONS = {
    "Building more resilient CNI: what industry pen testers told us": (
        "打造更具韌性的關鍵國家基礎設施：產業滲透測試人員的回饋"
    ),
    "Cyber Shield: The path to an agentic AI future for cyber defence": "Cyber Shield：邁向具代理式 AI 的網路防禦未來",
}


async def translate_titles_async(
    unique_titles: list[str],
    translator_class: Any,
    content_label: str,
    *,
    concurrency: int,
    request_timeout: float,
    budget: float,
) -> dict[str, str]:
    semaphore = asyncio.Semaphore(concurrency)
    deadline = asyncio.get_running_loop().time() + budget

    async with translator_class() as translator:
        # HTTPX hooks observe actual requests including provider fallback calls;
        # cache hits and translation jobs that never start are not HTTP attempts.
        client = getattr(translator, "client", None)
        if client is not None and isinstance(getattr(client, "event_hooks", None), dict):
            async def request_hook(request: Any) -> None:
                http_attempt("translation")

            async def response_hook(response: Any) -> None:
                http_status("translation", response.status_code)

            client.event_hooks.setdefault("request", []).append(request_hook)
            client.event_hooks.setdefault("response", []).append(response_hook)

        async def translate_one(title: str) -> tuple[str, str]:
            translated_title = ""
            async with semaphore:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    print(f"[warn] {content_label}翻譯已達 {budget} 秒時限，保留英文：{title}")
                    return title, translated_title
                try:
                    translated = await asyncio.wait_for(
                        translator.translate(title, src="en", dest="zh-tw"),
                        timeout=min(request_timeout, remaining),
                    )
                except Exception as exc:
                    print(f"[warn] googletrans {content_label}翻譯失敗，保留英文：{title} ({exc})")
                else:
                    translated_title = translated.text
            return title, translated_title

        results = await asyncio.gather(*(translate_one(title) for title in unique_titles))
    return {title: _translation_or_fallback(title, translated_title) for title, translated_title in results}


def _translation_or_fallback(title: str, translated_title: str) -> str:
    if translated_title and normalize_title(translated_title) != normalize_title(title):
        return str(translated_title)
    return (
        MANUAL_TITLE_TRANSLATIONS.get(title.strip(), "")
        or _translate_election_statement_title(title)
        or translated_title
    )


def _translate_titles_with_deep_translator(unique_titles: list[str]) -> dict[str, str]:
    return {
        title: _translate_with_deep_translator(title) or _translate_election_statement_title(title)
        for title in unique_titles
    }


def _translate_with_deep_translator(title: str) -> str:
    manual = MANUAL_TITLE_TRANSLATIONS.get(title.strip())
    if manual:
        return manual
    try:
        from deep_translator import GoogleTranslator  # type: ignore[import-untyped]
    except ImportError:
        print("[warn] 尚未安裝 deep-translator，無法執行備援翻譯。請先執行：pip install -r requirement.txt")
        return ""

    try:
        translated_title = GoogleTranslator(source="en", target="zh-TW").translate(title)
    except Exception as exc:
        print(f"[warn] deep-translator 標題翻譯失敗：{title} ({exc})")
        return ""

    if translated_title and normalize_title(translated_title) != normalize_title(title):
        return str(translated_title)
    return ""


def _translate_election_statement_title(title: str) -> str:
    match = re.fullmatch(
        r"Post count statement\s*[-–]\s*(\d{4})\s+(.+?)\s+election",
        title,
        flags=re.IGNORECASE,
    )
    if match:
        year, election_name = match.groups()
        return f"計票後聲明 - {year} 年{_translate_election_name(election_name)}選舉"

    match = re.fullmatch(r"Post poll statement\s*[-–]\s*(.+)", title, flags=re.IGNORECASE)
    if match:
        return f"投票後聲明 - {_translate_month_year(match.group(1))}"

    return ""


def _translate_election_name(name: str) -> str:
    known_names = {
        "scottish parliament": "蘇格蘭議會",
        "senedd": "參議院",
    }
    return known_names.get(name.casefold(), name)


def _translate_month_year(value: str) -> str:
    months = {
        "january": "1 月",
        "february": "2 月",
        "march": "3 月",
        "april": "4 月",
        "may": "5 月",
        "june": "6 月",
        "july": "7 月",
        "august": "8 月",
        "september": "9 月",
        "october": "10 月",
        "november": "11 月",
        "december": "12 月",
    }
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", value.strip())
    if not match:
        return value
    month, year = match.groups()
    return f"{year} 年 {months.get(month.casefold(), month)}"
