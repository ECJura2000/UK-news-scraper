from __future__ import annotations

from collections.abc import Iterable
import re

from .models import NewsItem


def dedupe_news_items(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen: set[tuple[str, ...]] = set()
    output: list[NewsItem] = []
    for item in sorted(items, key=lambda news: news.published_at, reverse=True):
        key = news_item_key(item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def news_item_key(item: NewsItem) -> tuple[str, ...]:
    normalized_link = item.link.strip().rstrip("/").casefold()
    if normalized_link:
        return ("link", normalized_link)
    return (
        "fallback",
        item.agency.casefold(),
        item.date_text,
        normalize_title(item.title),
    )


def normalize_title(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[–—]", "-", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()
