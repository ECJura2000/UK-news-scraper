from __future__ import annotations

from urllib.parse import urljoin

import feedparser
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
        rel = " ".join(link.get("rel", [])).lower() if link.get("rel") else ""
        feed_type = (link.get("type") or "").lower()
        href = link.get("href")
        if not href:
            continue
        if "alternate" in rel and ("rss" in feed_type or "atom" in feed_type or "xml" in feed_type):
            urls.append(urljoin(page_url, href))
    return list(dict.fromkeys(urls))
