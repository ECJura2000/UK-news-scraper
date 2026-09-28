from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ...models import Agency, NewsItem
from .utils.date import parse_datetime_text
from .utils.dedupe import dedupe_items
from .utils.text import clean_text


def _attr_text(node: Tag, name: str) -> str:
    value = node.get(name)
    return value if isinstance(value, str) else ""


class SourceHtmlAdapter:
    agency: Agency

    def _extract_html_news_items(
        self,
        soup: BeautifulSoup,
        page_url: str,
        since: datetime,
    ) -> list[NewsItem] | None:
        if self.agency.short_name == "Electoral Commission":
            return self._extract_electoral_commission_items(soup, page_url, since)
        if self.agency.short_name == "NPSA":
            return self._extract_npsa_items(soup, page_url, since)
        if self.agency.short_name == "Ofcom":
            return self._extract_ofcom_items(soup, page_url, since)
        return None

    def _extract_electoral_commission_items(
        self,
        soup: BeautifulSoup,
        page_url: str,
        since: datetime,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []
        for article in soup.select("article.c-teaser"):
            anchor = article.find("a", href=True)
            title_node = article.select_one(".c-teaser__title")
            time_node = article.find("time")
            if not anchor or not title_node or not time_node:
                continue
            published_at = parse_datetime_text(_attr_text(time_node, "datetime") or time_node.get_text(" ", strip=True))
            if not published_at or published_at < since:
                continue
            summary_node = article.select_one(".c-teaser__desc")
            items.append(
                self._html_news_item(
                    title=title_node.get_text(" ", strip=True),
                    link=urljoin(page_url, _attr_text(anchor, "href")),
                    published_at=published_at,
                    source_feed=page_url,
                    summary=summary_node.get_text(" ", strip=True) if summary_node else "",
                )
            )
        return dedupe_items(items)

    def _extract_npsa_items(
        self,
        soup: BeautifulSoup,
        page_url: str,
        since: datetime,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []
        rows = soup.select(".views-row")
        for row in rows:
            anchor = row.select_one("h2 a[href], h3 a[href], .views-field-title a[href]")
            if not anchor:
                continue
            published_at = _date_from_text(
                row.get_text(" ", strip=True), r"Blog publish date is\s+(\d{1,2}/\d{1,2}/\d{4})"
            )
            if not published_at or published_at < since:
                continue
            summary = _summary_from_row(row)
            items.append(
                self._html_news_item(
                    title=anchor.get_text(" ", strip=True),
                    link=urljoin(page_url, _attr_text(anchor, "href")),
                    published_at=published_at,
                    source_feed=page_url,
                    summary=summary,
                )
            )
        return dedupe_items(items)

    def _extract_ofcom_items(
        self,
        soup: BeautifulSoup,
        page_url: str,
        since: datetime,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []
        for anchor in soup.find_all("a", href=True):
            text = clean_text(anchor.get_text(" ", strip=True))
            if "Published:" not in text:
                continue
            published_at = _date_from_text(text, r"Published:\s+(\d{1,2}\s+\w+\s+\d{4})")
            if not published_at or published_at < since:
                continue
            title = clean_text(text.split("Published:", 1)[0])
            if len(title) < 12:
                continue
            items.append(
                self._html_news_item(
                    title=title,
                    link=urljoin(page_url, _attr_text(anchor, "href")),
                    published_at=published_at,
                    source_feed=page_url,
                )
            )
        return dedupe_items(items)

    def _html_news_item(
        self,
        title: str,
        link: str,
        published_at: datetime,
        source_feed: str,
        summary: str = "",
        content_type: str = "news",
    ) -> NewsItem:
        return NewsItem(
            agency=self.agency.display_name,
            agency_en=self.agency.name_en,
            unit_category=self.agency.short_name,
            title=clean_text(title),
            link=link,
            published_at=published_at,
            summary=clean_text(summary),
            source_feed=source_feed,
            content_type=content_type,
        )


def _date_from_text(text: str, pattern: str) -> datetime | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return parse_datetime_text(match.group(1))


def _summary_from_row(row: Any) -> str:
    paragraphs = [
        clean_text(paragraph.get_text(" ", strip=True))
        for paragraph in row.find_all("p")
        if "readmore" not in paragraph.get("class", [])
    ]
    return " ".join(paragraph for paragraph in paragraphs if paragraph and paragraph != "Latest Blog")
