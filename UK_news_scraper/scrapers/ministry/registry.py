from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ...config import (
    AGENCIES,
    DEFAULT_MAX_WORKERS,
    TOPIC_RULES,
)
from ...http.async_client import get_text
from ...errors import DownloadError, UKNewsError
from ...models import Agency, NewsItem, ParliamentBriefing
from ...rss import discover_feed_urls, parse_feed
from ..base import Scraper
from .utils.date import parse_datetime_text, parse_feed_datetime
from .utils.dedupe import dedupe_items
from .utils.text import clean_text, keyword_in_text, normalize_for_match
from .status import AgencyFetchStatus, FetchAllResult, health_warning as _health_warning, newest_published_at as _newest_published_at

__all__ = [
    "AgencyFetchStatus",
    "FetchAllResult",
    "_health_warning",
    "_newest_published_at",
    "AgencyFeedScraper",
    "apply_parliament_topic_filter",
    "apply_topic_filter",
    "build_scrapers",
    "fetch_all",
    "fetch_all_with_status",
]


RETRY_DELAY_SECONDS = 2
ELECTORAL_COMMISSION_GOOGLE_NEWS_EXCLUDED_TITLES = {
    "search criteria",
    "home page | electoral commission",
    "donation summary",
    "loan summary",
    "qualifications",
    "living abroad",
    "resources for media",
}


class AgencyFeedScraper(Scraper):
    def __init__(self, agency: Agency) -> None:
        self.agency = agency

    def fetch(self, since: datetime) -> list[NewsItem]:
        if self.agency.short_name == "NPSA":
            return self._fetch_google_news_fallback(since)

        items: list[NewsItem] = []
        attempted_sources = 0
        successful_sources = 0
        feed_urls = list(self.agency.feeds)
        if not feed_urls:
            feed_urls.extend(discover_feed_urls(self.agency.homepage))
        for page in self.agency.news_pages:
            feed_urls.extend(discover_feed_urls(page))

        for feed_url in list(dict.fromkeys(feed_urls)):
            attempted_sources += 1
            try:
                feed = parse_feed(feed_url)
            except (UKNewsError, OSError, ValueError, KeyError, TypeError) as exc:
                print(f"[warn] RSS/Atom 讀取失敗：{self.agency.short_name} {feed_url} ({exc})")
                continue
            successful_sources += 1

            for entry in feed.entries:
                try:
                    item = self._entry_to_news_item(entry, feed_url, since)
                except (UKNewsError, OSError, ValueError, KeyError, TypeError) as exc:
                    print(f"[warn] 單筆 RSS 解析失敗：{self.agency.short_name} {feed_url} ({exc})")
                    continue
                if item:
                    items.append(item)

        if not items and self.agency.news_pages:
            html_items, html_attempted, html_successful = self._fetch_html_news_pages(since)
            attempted_sources += html_attempted
            successful_sources += html_successful
            items.extend(html_items)

        if attempted_sources and not successful_sources and self.agency.short_name in (
            "Ofcom",
            "NPSA",
            "Electoral Commission",
        ):
            attempted_sources += 1
            try:
                fallback_items = self._fetch_google_news_fallback(since)
            except Exception as exc:
                print(f"[warn] Google News 備援讀取失敗：{self.agency.short_name} ({exc})")
            else:
                successful_sources += 1
                items.extend(fallback_items)

        if attempted_sources and not successful_sources:
            raise DownloadError("所有來源讀取失敗")

        return dedupe_items(items)

    def _entry_to_news_item(self, entry: Any, feed_url: str, since: datetime) -> NewsItem | None:
        published_at = parse_feed_datetime(entry)
        if not published_at or published_at < since:
            return None

        title = clean_text(getattr(entry, "title", ""))
        link = getattr(entry, "link", "")
        summary = _entry_summary(entry)
        if not title or not link:
            return None
        if not self._is_allowed_link(link):
            return None

        return NewsItem(
            agency=self.agency.display_name,
            agency_en=self.agency.name_en,
            unit_category=self.agency.short_name,
            title=title,
            link=link,
            published_at=published_at,
            summary=summary,
            source_feed=feed_url,
        )

    def _is_allowed_link(self, link: str) -> bool:
        patterns = self.agency.link_include_patterns
        if not patterns:
            return True
        return any(pattern in link for pattern in patterns)

    def _fetch_html_news_pages(self, since: datetime) -> tuple[list[NewsItem], int, int]:
        items: list[NewsItem] = []
        attempted_sources = 0
        successful_sources = 0
        for page_url in self.agency.news_pages:
            attempted_sources += 1
            try:
                soup = BeautifulSoup(get_text(page_url), "html.parser")
            except Exception as exc:
                print(f"[warn] 新聞頁讀取失敗：{self.agency.short_name} {page_url} ({exc})")
                continue
            successful_sources += 1
            page_items = self._extract_html_news_items(soup, page_url, since)
            if page_items is not None:
                items.extend(page_items)
                continue

            for anchor in soup.find_all("a", href=True):
                title = clean_text(anchor.get_text(" ", strip=True))
                if len(title) < 12:
                    continue
                link = anchor["href"]
                if link.startswith("/"):
                    link = urljoin(page_url, link)
                if not link.startswith("http"):
                    continue

                date_text = ""
                parent = anchor.find_parent(["article", "li", "div"]) or anchor
                time_tag = parent.find("time") if parent else None
                if time_tag:
                    date_text = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
                published_at = parse_datetime_text(date_text)
                if not published_at or published_at < since:
                    continue
                items.append(
                    NewsItem(
                        agency=self.agency.display_name,
                        agency_en=self.agency.name_en,
                        unit_category=self.agency.short_name,
                        title=title,
                        link=link,
                        published_at=published_at,
                        source_feed=page_url,
                    )
                )
        return dedupe_items(items), attempted_sources, successful_sources

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
            published_at = parse_datetime_text(time_node.get("datetime") or time_node.get_text(" ", strip=True))
            if not published_at or published_at < since:
                continue
            summary_node = article.select_one(".c-teaser__desc")
            items.append(
                self._html_news_item(
                    title=title_node.get_text(" ", strip=True),
                    link=urljoin(page_url, anchor["href"]),
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
            published_at = _date_from_text(row.get_text(" ", strip=True), r"Blog publish date is\s+(\d{1,2}/\d{1,2}/\d{4})")
            if not published_at or published_at < since:
                continue
            summary = _summary_from_row(row)
            items.append(
                self._html_news_item(
                    title=anchor.get_text(" ", strip=True),
                    link=urljoin(page_url, anchor["href"]),
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
                    link=urljoin(page_url, anchor["href"]),
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
        )

    def _fetch_google_news_fallback(self, since: datetime) -> list[NewsItem]:
        query_text = {
            "Ofcom": "site:ofcom.org.uk Ofcom",
            "NPSA": "site:npsa.gov.uk NPSA",
            "Electoral Commission": "site:electoralcommission.org.uk Electoral Commission",
        }[self.agency.short_name]
        query = quote(query_text)
        feed_url = f"https://news.google.com/rss/search?q={query}&hl=en-GB&gl=GB&ceid=GB:en"
        feed = parse_feed(feed_url)

        items: list[NewsItem] = []
        for entry in feed.entries:
            published_at = parse_feed_datetime(entry)
            if not published_at or published_at < since:
                continue
            title = clean_text(getattr(entry, "title", ""))
            if self.agency.short_name == "Ofcom":
                if "www.ofcom.org.uk" not in title:
                    continue
                title = re.sub(r"\s+-\s+(Ofcom\s+-\s+)?www\.ofcom\.org\.uk$", "", title).strip()
            elif self.agency.short_name == "NPSA":
                title = re.sub(
                    r"\s+-\s+National Protective Security Authority(?:\s+\|\s+NPSA)?$",
                    "",
                    title,
                    flags=re.IGNORECASE,
                ).strip()
            elif self.agency.short_name == "Electoral Commission":
                title = re.sub(
                    r"\s+-\s+Electoral Commission$",
                    "",
                    title,
                    flags=re.IGNORECASE,
                ).strip()
                if not _is_electoral_commission_google_news_title(title):
                    continue
            if len(title) < 12:
                continue
            items.append(
                self._html_news_item(
                    title=title,
                    link=getattr(entry, "link", ""),
                    published_at=published_at,
                    source_feed=feed_url,
                    summary=clean_text(getattr(entry, "summary", "")),
                )
            )
        print(f"[info] {self.agency.short_name} 官方站受 Cloudflare 阻擋，改用 Google News RSS 備援：{len(items)} 筆")
        return dedupe_items(items)


def _is_electoral_commission_google_news_title(title: str) -> bool:
    normalized = clean_text(title).casefold()
    if not normalized or normalized in ELECTORAL_COMMISSION_GOOGLE_NEWS_EXCLUDED_TITLES:
        return False
    return not any(
        normalized.startswith(prefix)
        for prefix in (
            "search criteria",
            "donation summary",
            "loan summary",
        )
    )


def build_scrapers(agencies: tuple[Agency, ...] = AGENCIES) -> list[AgencyFeedScraper]:
    return [AgencyFeedScraper(agency) for agency in agencies]


def apply_topic_filter(items: list[NewsItem]) -> list[NewsItem]:
    filtered: list[NewsItem] = []
    for item in items:
        match = _assess_relevance(item.title, item.summary)
        if match["score"] >= 3:
            item.matched_topics = match["topics"]
            item.matched_keywords = match["keywords"]
            item.title_matched_keywords = match["title_keywords"]
            item.summary_matched_keywords = match["summary_keywords"]
            item.relevance_score = match["score"]
            item.relevance_level = _relevance_level(match["score"])
            filtered.append(item)

    return dedupe_items(filtered)


def apply_parliament_topic_filter(items: list[ParliamentBriefing]) -> list[ParliamentBriefing]:
    filtered: list[ParliamentBriefing] = []
    for item in items:
        match = _assess_relevance(item.title, item.summary)
        if match["score"] >= 3:
            item.matched_topics = match["topics"]
            item.matched_keywords = match["keywords"]
            item.title_matched_keywords = match["title_keywords"]
            item.summary_matched_keywords = match["summary_keywords"]
            item.relevance_score = match["score"]
            item.relevance_level = _relevance_level(match["score"])
            filtered.append(item)
    return filtered


def _matched_topics_and_keywords(haystack: str) -> tuple[list[str], list[str]]:
    topics: list[str] = []
    keywords: list[str] = []
    for rule in TOPIC_RULES:
        matched = [keyword for keyword in rule.keywords if keyword_in_text(keyword, haystack)]
        if matched:
            topics.append(rule.name)
            keywords.extend(matched)
    return sorted(set(topics)), sorted(set(keywords), key=str.casefold)


# Useful supporting signals that are too broad to qualify an item by themselves.
_BROAD_KEYWORDS = {
    "copyright", "innovation", "platform", "resilience", "supply chain", "technology",
}


def _assess_relevance(title: str, summary: str) -> dict[str, object]:
    title_topics, title_keywords = _matched_topics_and_keywords(normalize_for_match(title))
    summary_topics, summary_keywords = _matched_topics_and_keywords(normalize_for_match(summary))
    keywords = sorted(set(title_keywords + summary_keywords), key=str.casefold)
    topics = sorted(set(title_topics + summary_topics))

    score = sum(2 if keyword.casefold() in _BROAD_KEYWORDS else 4 for keyword in title_keywords)
    score += sum(1 if keyword.casefold() in _BROAD_KEYWORDS else 3 for keyword in summary_keywords)
    if len({keyword.casefold() for keyword in keywords}) >= 2:
        score += 1
    if len(topics) >= 2:
        score += 1
    return {
        "topics": topics,
        "keywords": keywords,
        "title_keywords": title_keywords,
        "summary_keywords": summary_keywords,
        "score": score,
    }


def _relevance_level(score: int) -> str:
    if score >= 8:
        return "高"
    if score >= 5:
        return "中"
    return "低"


def fetch_all_with_status(since: datetime, max_workers: int = DEFAULT_MAX_WORKERS) -> FetchAllResult:
    from .orchestration import fetch_all_with_status as orchestrated_fetch_all_with_status

    return orchestrated_fetch_all_with_status(since, max_workers=max_workers)


def fetch_all(since: datetime, max_workers: int = DEFAULT_MAX_WORKERS) -> list[NewsItem]:
    from .orchestration import fetch_all as orchestrated_fetch_all

    return orchestrated_fetch_all(since, max_workers=max_workers)


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


def _entry_summary(entry: Any) -> str:
    for attr in ("summary", "description"):
        value = getattr(entry, attr, "")
        if value:
            return clean_text(str(value))

    content = getattr(entry, "content", "")
    if isinstance(content, list):
        return clean_text(" ".join(str(part.get("value", part)) for part in content))
    return clean_text(str(content))
