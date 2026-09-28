from __future__ import annotations

from urllib.parse import urljoin

import feedparser  # type: ignore[import-untyped]
from bs4 import BeautifulSoup

from ..http.async_client import get_text


def parse_feed(url: str) -> feedparser.FeedParserDict:
    feed = feedparser.parse(get_text(url))
    if getattr(feed, "bozo", False) and not feed.entries:
        raise ValueError(f"feed 解析失敗：{getattr(feed, 'bozo_exception', 'unknown error')}")
    return feed


def discover_feed_urls(page_url: str) -> list[str]:
    try:
        html = get_text(page_url)
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.find_all("link"):
        rel_value = link.get("rel")
        rel = " ".join(rel_value).lower() if isinstance(rel_value, list) else str(rel_value or "").lower()
        feed_type_value = link.get("type")
        feed_type = feed_type_value.lower() if isinstance(feed_type_value, str) else ""
        href = link.get("href")
        if not isinstance(href, str) or not href:
            continue
        if "alternate" in rel and ("rss" in feed_type or "atom" in feed_type or "xml" in feed_type):
            urls.append(urljoin(page_url, href))
    return list(dict.fromkeys(urls))
