from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from ...article_links import is_agency_homepage
from ...catalog_html import content_type_for_link as _content_type_for_link
from ...catalog_html import parse_news_index
from ...config import (
    AGENCIES,
    DEFAULT_MAX_WORKERS,
    DEFAULT_TIMEZONE,
)
from ...errors import DownloadError, UKNewsError
from ...http.async_client import get_json, get_text
from ...models import Agency, NewsItem, ParliamentBriefing
from ...profiles import FilterProfile
from ...relevance import apply_profile_filter
from ...rss import discover_feed_urls, parse_feed
from ...source_catalog import catalog_adapter
from ..base import Scraper
from .source_adapters import SourceHtmlAdapter, _attr_text
from .status import AgencyFetchStatus, FetchAllResult
from .status import health_warning as _health_warning
from .status import newest_published_at as _newest_published_at
from .utils.date import parse_datetime_text, parse_feed_datetime
from .utils.dedupe import dedupe_items
from .utils.text import clean_text

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


class AgencyFeedScraper(SourceHtmlAdapter, Scraper):
    def __init__(self, agency: Agency, until: datetime | None = None) -> None:
        self.agency = agency
        self.until = until
        self.source_warnings: list[str] = []
        self.candidate_count = 0

    def fetch(self, since: datetime) -> list[NewsItem]:
        self.source_warnings = []
        self.candidate_count = 0
        adapter = catalog_adapter(self.agency.short_name)
        if adapter == "html_news":
            html_items: list[NewsItem] = []
            successes = 0
            for page in self.agency.news_pages:
                try:
                    html = get_text(page)
                except Exception as exc:
                    self.source_warnings.append(f"{self.agency.short_name} 官方發布頁讀取失敗：{exc}")
                    continue
                successes += 1
                found = parse_news_index(html, self.agency, page, since, self.until)
                all_dated = parse_news_index(html, self.agency, page, datetime(1990, 1, 1, tzinfo=since.tzinfo), None)
                self.candidate_count += len(found)
                if all_dated and min(x.published_at for x in all_dated) > since:
                    self.source_warnings.append(
                        f"{self.agency.short_name} 官方列表最舊資料晚於查詢起日，期間可能不完整"
                    )
                if not all_dated:
                    self.source_warnings.append(
                        f"{self.agency.short_name} 官方列表未解析到有日期的資料，請確認頁面格式"
                    )
                html_items.extend(found)
            if not successes:
                raise DownloadError("所有官方發布頁讀取失敗")
            return dedupe_items(html_items)
        if self.agency.short_name.startswith("govuk:") and adapter != "feed":
            return self._fetch_govuk_search(since)
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
            feed_candidates = 0
            feed_parsed = 0
            if self.agency.short_name.startswith("court-") or catalog_adapter(self.agency.short_name) == "feed":
                dates = [value for entry in feed.entries if (value := parse_feed_datetime(entry))]
                if dates and min(dates) > since:
                    self.source_warnings.append(
                        f"{self.agency.short_name} 官方 RSS 最舊資料晚於查詢起日，期間可能不完整"
                    )

            for entry in feed.entries:
                entry_date = parse_feed_datetime(entry)
                entry_link = getattr(entry, "link", "")
                if (
                    entry_date is None or (entry_date >= since and (self.until is None or entry_date < self.until))
                ) and (not entry_link or self._is_allowed_link(entry_link)):
                    feed_candidates += 1
                try:
                    item = self._entry_to_news_item(entry, feed_url, since)
                except (UKNewsError, OSError, ValueError, KeyError, TypeError) as exc:
                    print(f"[warn] 單筆 RSS 解析失敗：{self.agency.short_name} {feed_url} ({exc})")
                    continue
                if item:
                    feed_parsed += 1
                    feed_items.append(item)
            self.candidate_count += feed_candidates
            if feed_candidates and not feed_parsed:
                self.source_warnings.append(f"{self.agency.short_name} RSS 有候選資料但解析為零筆：{feed_url}")

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

    def _fetch_govuk_search(self, since: datetime) -> list[NewsItem]:
        """Use GOV.UK's organisation/date search, paging beyond the Atom window."""
        slug = self.agency.short_name.removeprefix("govuk:")
        items: list[NewsItem] = []
        start = 0
        for _ in range(50):
            query = urlencode(
                {
                    "filter_organisations": slug,
                    "filter_public_timestamp": (
                        f"from:{since.date().isoformat()},to:{self.until.date().isoformat()}"
                        if self.until
                        else f"from:{since.date().isoformat()}"
                    ),
                    "fields": "title,link,description,public_timestamp,format",
                    "order": "-public_timestamp",
                    "count": 100,
                    "start": start,
                }
            )
            url = f"https://www.gov.uk/api/search.json?{query}"
            try:
                payload = get_json(url)
            except Exception as exc:
                if items:
                    self.source_warnings.append(f"{self.agency.short_name} 搜尋分頁中斷，已保留取得的資料")
                    return dedupe_items(items)
                raise DownloadError(f"GOV.UK 搜尋失敗：{slug}（{type(exc).__name__}：{exc}）") from exc
            results = payload.get("results", [])
            if not isinstance(results, list):
                if items:
                    self.source_warnings.append(f"{self.agency.short_name} 搜尋分頁格式異常，已保留取得的資料")
                    return dedupe_items(items)
                raise DownloadError(f"GOV.UK 搜尋格式錯誤：{slug}")
            for value in results:
                if not value.get("link"):
                    self.source_warnings.append(f"{self.agency.short_name} GOV.UK 搜尋資料缺少連結")
                    continue
                link = urljoin("https://www.gov.uk", str(value.get("link", "")))
                document_format = str(value.get("format", "")).casefold()
                is_decision = "decision" in document_format or "judgment" in document_format
                timestamp = str(value.get("public_timestamp", ""))
                if not (
                    self._is_allowed_link(link) or (is_decision and urlparse(link).hostname in {"gov.uk", "www.gov.uk"})
                ):
                    continue
                if not timestamp:
                    self.source_warnings.append(f"{self.agency.short_name} GOV.UK 搜尋資料缺少發布日期")
                    continue
                try:
                    published_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    self.source_warnings.append(f"{self.agency.short_name} GOV.UK 搜尋日期格式異常")
                    continue
                if published_at < since:
                    continue
                if self.until is not None and published_at >= self.until:
                    continue
                self.candidate_count += 1
                title = clean_text(str(value.get("title", "")))
                if not title:
                    self.source_warnings.append(f"{self.agency.short_name} GOV.UK 搜尋資料缺少標題")
                    continue
                items.append(
                    NewsItem(
                        agency=self.agency.display_name,
                        agency_en=self.agency.name_en,
                        unit_category=self.agency.short_name,
                        title=title,
                        link=link,
                        published_at=published_at,
                        summary=clean_text(str(value.get("description", ""))),
                        source_feed=url,
                        content_type="judgment" if is_decision else _content_type_for_link(link, title),
                    )
                )
            start += len(results)
            if not results or start >= int(payload.get("total", start)):
                return dedupe_items(items)
        self.source_warnings.append(f"{self.agency.short_name} 搜尋結果超過 5000 筆，請縮短期間")
        return dedupe_items(items)

    def _entry_to_news_item(self, entry: Any, feed_url: str, since: datetime) -> NewsItem | None:
        published_at = parse_feed_datetime(entry)
        if not published_at or published_at < since:
            return None
        if self.until is not None and published_at >= self.until:
            return None

        raw_title = getattr(entry, "title", "")
        if getattr(entry, "title_detail", {}).get("type") == "text/plain":
            raw_title = html.escape(raw_title)
        title = clean_text(raw_title)
        link = getattr(entry, "link", "")
        summary = _entry_summary(entry)
        if not title or not link:
            return None
        if not self._is_allowed_link(link):
            return None
        if catalog_adapter(self.agency.short_name) == "feed":
            link_host = (urlparse(link).hostname or "").casefold().removeprefix("www.")
            official_hosts = [
                (urlparse(url).hostname or "").casefold().removeprefix("www.")
                for url in (self.agency.homepage, *self.agency.news_pages, *self.agency.official_pages)
            ]
            if not link_host or not any(
                official
                and (link_host == official or link_host.endswith(f".{official}") or official.endswith(f".{link_host}"))
                for official in official_hosts
            ):
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
            content_type="judgment"
            if self.agency.short_name.endswith(":judgments")
            else _content_type_for_link(link, title),
        )

    def _is_allowed_link(self, link: str) -> bool:
        if is_agency_homepage(link, self.agency.homepage):
            return False
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
                if not page_items and _page_has_in_range_date(soup, since, self.until):
                    self.candidate_count += 1
                    self.source_warnings.append(f"{self.agency.short_name} 新聞頁有期間內日期但解析為零筆：{page_url}")
                items.extend(page_items)
                continue

            before_count = len(items)
            for anchor in soup.find_all("a", href=True):
                title = clean_text(anchor.get_text(" ", strip=True))
                if len(title) < 12:
                    continue
                link = _attr_text(anchor, "href")
                if link.startswith("/"):
                    link = urljoin(page_url, link)
                if not link.startswith("http"):
                    continue

                date_text = ""
                parent = anchor.find_parent(["article", "li", "div"]) or anchor
                time_tag = parent.find("time") if parent else None
                if time_tag:
                    date_text = _attr_text(time_tag, "datetime") or time_tag.get_text(" ", strip=True)
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
            if len(items) == before_count and _page_has_in_range_date(soup, since, self.until):
                self.candidate_count += 1
                self.source_warnings.append(f"{self.agency.short_name} 新聞頁有期間內日期但解析為零筆：{page_url}")
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
            date_scope = (
                soup.select("article, li, .search-result, .card")
                if is_agency_homepage(page_url, self.agency.homepage)
                else [soup]
            )
            if not page_items and any(_page_has_in_range_date(node, since, self.until) for node in date_scope):
                self.candidate_count += 1
                self.source_warnings.append(f"{self.agency.short_name} 官方頁有期間內日期但解析為零筆：{page_url}")
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
            link = urljoin(page_url, _attr_text(anchor, "href"))
            if (
                not self._is_official_link(link, page_url)
                or not self._is_allowed_link(link)
                or link.rstrip("/") in seen_links
            ):
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
            for marker in (
                "/collection/",
                "/guidance/",
                "/government/publications/",
                "/government/consultations/",
                "/report",
            )
        )
        if is_agency_homepage(page_url, self.agency.homepage):
            return None
        if not is_content_page and not has_article_metadata:
            return None
        title_node = soup.select_one("h1") or soup.select_one('meta[property="og:title"]') or soup.find("title")
        title = clean_text(
            _attr_text(title_node, "content")
            if title_node and title_node.name == "meta"
            else title_node.get_text(" ", strip=True)
            if title_node
            else ""
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

    def _fetch_google_news_fallback(self, since: datetime) -> list[NewsItem]:
        query_texts = self._google_news_query_texts()
        items: list[NewsItem] = []
        for query_text in query_texts:
            items.extend(self._fetch_google_news_query(query_text, since))
        print(
            f"[info] {self.agency.short_name} 改用 Google News RSS 備援（{len(query_texts)} 組查詢）：{len(items)} 筆"
        )
        if items:
            self.source_warnings.append(
                f"{self.agency.short_name} 使用 Google News 備援；日期取自備援 RSS，未核對官方發布日期"
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
            if self.until is not None and published_at >= self.until:
                continue
            expected_host = {
                "Ofcom": "ofcom.org.uk",
                "NPSA": "npsa.gov.uk",
                "Electoral Commission": "electoralcommission.org.uk",
            }[self.agency.short_name]
            publisher_url = getattr(entry, "source", {}).get("href", "")
            if (
                publisher_url
                and (urlparse(publisher_url).hostname or "").casefold().removeprefix("www.") != expected_host
            ):
                self.source_warnings.append(f"{self.agency.short_name} 備援資料發布者不符，已排除")
                continue
            link = getattr(entry, "link", "")
            link_host = (urlparse(link).hostname or "").casefold().removeprefix("www.")
            if link_host not in {expected_host, "news.google.com"} or is_agency_homepage(link, self.agency.homepage):
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
        parsed = parse_datetime_text(_attr_text(meta, "content"))
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
    description = node.select_one('meta[property="og:description"], meta[name="description"]')
    if description:
        return clean_text(_attr_text(description, "content"))
    for selector in (".summary", ".description", ".govuk-body", "p"):
        paragraph = node.select_one(selector)
        if paragraph:
            text = clean_text(paragraph.get_text(" ", strip=True))
            if text:
                return text
    return ""


def build_scrapers(agencies: tuple[Agency, ...] = AGENCIES, until: datetime | None = None) -> list[AgencyFeedScraper]:
    return [AgencyFeedScraper(agency, until) for agency in agencies]


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
    until: datetime | None = None,
) -> FetchAllResult:
    from .orchestration import fetch_all_with_status as orchestrated_fetch_all_with_status

    return orchestrated_fetch_all_with_status(
        since,
        max_workers=max_workers,
        agencies=agencies,
        until=until,
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


def _page_has_in_range_date(soup: Tag, since: datetime, until: datetime | None) -> bool:
    start_date = since.astimezone(ZoneInfo(DEFAULT_TIMEZONE)).date()
    end_date = until.astimezone(ZoneInfo(DEFAULT_TIMEZONE)).date() if until else None
    for node in soup.select("time[datetime], meta[property='article:published_time'], meta[name='datePublished']"):
        value = _attr_text(node, "datetime") or _attr_text(node, "content")
        published = parse_datetime_text(value)
        if published and published.date() >= start_date and (end_date is None or published.date() < end_date):
            return True
    return False


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
