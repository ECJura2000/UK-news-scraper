from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from ...config import (
    AGENCIES,
    DEFAULT_MAX_WORKERS,
)
from ...http.async_client import get_text
from ...errors import DownloadError, UKNewsError
from ...models import Agency, NewsItem, ParliamentBriefing
from ...profiles import FilterProfile
from ...relevance import apply_profile_filter
from ...rss import discover_feed_urls, parse_feed
from ..base import Scraper
from .utils.date import parse_datetime_text, parse_feed_datetime
from .utils.dedupe import dedupe_items
from .utils.text import clean_text
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
OFCOM_GOOGLE_NEWS_QUERIES = (
    "site:ofcom.org.uk Ofcom",
    'site:ofcom.org.uk "Ofcom statement"',
    'site:ofcom.org.uk "Ofcom consultation"',
    'site:ofcom.org.uk "Ofcom update"',
    'site:ofcom.org.uk "Ofcom news"',
    'site:ofcom.org.uk "Ofcom report"',
)


class AgencyFeedScraper(Scraper):
    def __init__(self, agency: Agency) -> None:
        self.agency = agency
        self.source_warnings: list[str] = []

    def fetch(self, since: datetime) -> list[NewsItem]:
        self.source_warnings = []
        if self.agency.short_name == "NPSA":
            official_items, _, _ = self._fetch_official_pages(since)
            if official_items:
                return official_items
            if self.agency.news_pages:
                html_items, _, _ = self._fetch_html_news_pages(since)
                if html_items:
                    return html_items
            return self._fetch_google_news_fallback(since)

        items: list[NewsItem] = []
        feed_items: list[NewsItem] = []
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
                self.source_warnings.append(f"{self.agency.short_name} RSS/Atom 讀取失敗：{feed_url}")
                continue
            successful_sources += 1

            for entry in feed.entries:
                try:
                    item = self._entry_to_news_item(entry, feed_url, since)
                except (UKNewsError, OSError, ValueError, KeyError, TypeError) as exc:
                    print(f"[warn] 單筆 RSS 解析失敗：{self.agency.short_name} {feed_url} ({exc})")
                    continue
                if item:
                    feed_items.append(item)

        if not feed_items and self.agency.news_pages:
            html_items, html_attempted, html_successful = self._fetch_html_news_pages(since)
            attempted_sources += html_attempted
            successful_sources += html_successful
            feed_items.extend(html_items)

        items.extend(feed_items)
        if self.agency.official_pages:
            official_items, official_attempted, official_successful = self._fetch_official_pages(since)
            attempted_sources += official_attempted
            successful_sources += official_successful
            items.extend(official_items)

        if not items and self.agency.short_name in (
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
            content_type=_content_type_for_link(link, title),
        )

    def _is_allowed_link(self, link: str) -> bool:
        patterns = self.agency.link_include_patterns
        if not patterns:
            return True
        return any(pattern in link for pattern in patterns)

    @staticmethod
    def _is_official_link(link: str, page_url: str) -> bool:
        link_host = urlparse(link).netloc.casefold().removeprefix("www.")
        page_host = urlparse(page_url).netloc.casefold().removeprefix("www.")
        return bool(link_host and link_host == page_host)

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

    def _fetch_official_pages(self, since: datetime) -> tuple[list[NewsItem], int, int]:
        items: list[NewsItem] = []
        attempted_sources = 0
        successful_sources = 0
        for page_url in self.agency.official_pages:
            attempted_sources += 1
            try:
                soup = BeautifulSoup(get_text(page_url), "html.parser")
                page_items = self._extract_official_page_items(soup, page_url, since)
            except Exception as exc:
                print(f"[warn] 官方補充頁讀取失敗：{self.agency.short_name} {page_url} ({exc})")
                self.source_warnings.append(f"{self.agency.short_name} 官方補充頁讀取失敗：{page_url}")
                continue
            successful_sources += 1
            items.extend(page_items)
        return dedupe_items(items), attempted_sources, successful_sources

    def _extract_official_page_items(
        self,
        soup: BeautifulSoup,
        page_url: str,
        since: datetime,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []
        page_item = self._extract_page_metadata_item(soup, page_url, since)
        if page_item:
            items.append(page_item)

        containers = soup.select("article, li, .govuk-document-list li, .search-result, .card")
        seen_links: set[str] = {page_item.link if page_item else ""}
        for container in containers:
            anchor = container.select_one("h1 a[href], h2 a[href], h3 a[href], h4 a[href], a[href]")
            if not anchor:
                continue
            link = urljoin(page_url, anchor.get("href", ""))
            if not self._is_official_link(link, page_url) or link.rstrip("/") in seen_links:
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            if len(title) < 12:
                continue
            published_at = _date_from_html(container)
            if not published_at or published_at < since:
                continue
            seen_links.add(link.rstrip("/"))
            items.append(
                self._html_news_item(
                    title=title,
                    link=link,
                    published_at=published_at,
                    source_feed=page_url,
                    summary=_summary_from_html(container),
                    content_type=_content_type_for_link(link, title, container.get_text(" ", strip=True)),
                )
            )
        return dedupe_items(items)

    def _extract_page_metadata_item(
        self,
        soup: BeautifulSoup,
        page_url: str,
        since: datetime,
    ) -> NewsItem | None:
        page_path = urlparse(page_url).path.casefold()
        has_article_metadata = bool(
            soup.select_one(
                'meta[property="article:published_time"], meta[property="datePublished"], '
                'script[type="application/ld+json"]'
            )
        )
        is_content_page = any(
            marker in page_path
            for marker in ("/collection/", "/guidance/", "/government/publications/", "/government/consultations/", "/report")
        )
        if not is_content_page and not has_article_metadata:
            return None
        title_node = soup.select_one("h1") or soup.select_one('meta[property="og:title"]') or soup.find("title")
        title = clean_text(
            title_node.get("content", "") if title_node and title_node.name == "meta" else title_node.get_text(" ", strip=True) if title_node else ""
        )
        published_at = _date_from_html(soup)
        if not title or len(title) < 12 or not published_at or published_at < since:
            return None
        return self._html_news_item(
            title=title,
            link=page_url,
            published_at=published_at,
            source_feed=page_url,
            summary=_summary_from_html(soup),
            content_type=_content_type_for_link(page_url, title, soup.get_text(" ", strip=True)),
        )

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

    def _fetch_google_news_fallback(self, since: datetime) -> list[NewsItem]:
        query_texts = self._google_news_query_texts()
        items: list[NewsItem] = []
        for query_text in query_texts:
            items.extend(self._fetch_google_news_query(query_text, since))
        print(
            f"[info] {self.agency.short_name} 改用 Google News RSS 備援"
            f"（{len(query_texts)} 組查詢）：{len(items)} 筆"
        )
        return dedupe_items(items)

    def _google_news_query_texts(self) -> tuple[str, ...]:
        if self.agency.short_name == "Ofcom":
            return OFCOM_GOOGLE_NEWS_QUERIES
        if self.agency.short_name == "NPSA":
            return ("site:npsa.gov.uk NPSA",)
        if self.agency.short_name == "Electoral Commission":
            return ("site:electoralcommission.org.uk Electoral Commission",)
        return ()

    def _fetch_google_news_query(self, query_text: str, since: datetime) -> list[NewsItem]:
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
        return items


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


def _date_from_html(node: Any) -> datetime | None:
    for time_node in node.select("time[datetime], time"):
        value = time_node.get("datetime") or time_node.get_text(" ", strip=True)
        parsed = parse_datetime_text(value)
        if parsed:
            return parsed
    for meta in node.select(
        'meta[property="article:published_time"], meta[property="datePublished"], '
        'meta[name="date"], meta[name="pubdate"]'
    ):
        parsed = parse_datetime_text(meta.get("content", ""))
        if parsed:
            return parsed
    for script in node.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for key in ("datePublished", "dateCreated", "dateModified"):
                parsed = parse_datetime_text(str(candidate.get(key, "")))
                if parsed:
                    return parsed
    text = clean_text(node.get_text(" ", strip=True))
    match = re.search(
        r"(?:published|publication|updated|posted)(?:\s+date)?\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return parse_datetime_text(match.group(1))
    return None


def _summary_from_html(node: Any) -> str:
    description = node.select_one(
        'meta[property="og:description"], meta[name="description"]'
    )
    if description:
        return clean_text(description.get("content", ""))
    for selector in (".summary", ".description", ".govuk-body", "p"):
        paragraph = node.select_one(selector)
        if paragraph:
            text = clean_text(paragraph.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _content_type_for_link(link: str, title: str = "", context: str = "") -> str:
    value = " ".join((link, title, context)).casefold()
    path = urlparse(link).path.casefold()
    if "/guidance/" in path or "/collection/" in path or "guidance" in value:
        return "guidance"
    if "/report" in path or "/research/" in path or "report" in value or "research" in value:
        return "report"
    if "/publication" in path or "/consultation" in path or "publication" in value or "consultation" in value:
        return "publication"
    return "news"


def build_scrapers(agencies: tuple[Agency, ...] = AGENCIES) -> list[AgencyFeedScraper]:
    return [AgencyFeedScraper(agency) for agency in agencies]


def apply_topic_filter(
    items: list[NewsItem],
    profile: FilterProfile | None = None,
) -> list[NewsItem]:
    return dedupe_items(apply_profile_filter(items, profile))


def apply_parliament_topic_filter(
    items: list[ParliamentBriefing],
    profile: FilterProfile | None = None,
) -> list[ParliamentBriefing]:
    return apply_profile_filter(items, profile)


def fetch_all_with_status(
    since: datetime,
    max_workers: int = DEFAULT_MAX_WORKERS,
    agencies: tuple[Agency, ...] | None = None,
) -> FetchAllResult:
    from .orchestration import fetch_all_with_status as orchestrated_fetch_all_with_status

    return orchestrated_fetch_all_with_status(
        since,
        max_workers=max_workers,
        agencies=agencies,
    )


def fetch_all(
    since: datetime,
    max_workers: int = DEFAULT_MAX_WORKERS,
    agencies: tuple[Agency, ...] | None = None,
) -> list[NewsItem]:
    from .orchestration import fetch_all as orchestrated_fetch_all

    return orchestrated_fetch_all(since, max_workers=max_workers, agencies=agencies)


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
