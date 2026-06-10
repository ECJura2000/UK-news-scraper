from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from time import monotonic, sleep
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ...config import (
    AGENCIES,
    DEFAULT_MAX_WORKERS,
    SOURCE_HEALTH_MAX_AGE_DAYS,
    SOURCE_HEALTH_MIN_ITEMS,
    TOPIC_RULES,
)
from ...http.async_client import get_text
from ...models import Agency, NewsItem, ParliamentBriefing, SourceHealth
from ...rss import discover_feed_urls, parse_feed
from ..base import Scraper
from .utils.date import parse_datetime_text, parse_feed_datetime
from .utils.dedupe import dedupe_items
from .utils.text import clean_text, keyword_in_text, normalize_for_match


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


@dataclass
class AgencyFetchStatus:
    agency_name: str
    success: bool
    source_name: str = ""
    item_count: int = 0
    attempts: int = 1
    error: str = ""
    duration_seconds: float = 0.0
    newest_published_at: str = ""
    warning: str = ""


@dataclass
class FetchAllResult:
    items: list[NewsItem]
    statuses: list[AgencyFetchStatus] = field(default_factory=list)

    @property
    def all_successful(self) -> bool:
        return all(status.success and not status.warning for status in self.statuses)

    @property
    def failed_statuses(self) -> list[AgencyFetchStatus]:
        return [status for status in self.statuses if not status.success]

    @property
    def source_health(self) -> list[SourceHealth]:
        return [
            SourceHealth(
                source=status.source_name,
                critical=True,
                success=status.success,
                item_count=status.item_count,
                duration_seconds=round(status.duration_seconds, 3),
                newest_published_at=status.newest_published_at,
                warning=status.warning or status.error,
            )
            for status in self.statuses
        ]


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
            except Exception as exc:
                print(f"[warn] RSS/Atom 讀取失敗：{self.agency.short_name} {feed_url} ({exc})")
                continue
            successful_sources += 1

            for entry in feed.entries:
                try:
                    item = self._entry_to_news_item(entry, feed_url, since)
                except Exception as exc:
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
            raise RuntimeError("所有來源讀取失敗")

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
        haystack = normalize_for_match(f"{item.title} {item.summary}")
        topics, keywords = _matched_topics_and_keywords(haystack)
        if topics:
            item.matched_topics = topics
            item.matched_keywords = keywords
            filtered.append(item)

    return dedupe_items(filtered)


def apply_parliament_topic_filter(items: list[ParliamentBriefing]) -> list[ParliamentBriefing]:
    filtered: list[ParliamentBriefing] = []
    for item in items:
        haystack = normalize_for_match(f"{item.title} {item.summary}")
        topics, keywords = _matched_topics_and_keywords(haystack)
        if topics:
            item.matched_topics = topics
            item.matched_keywords = keywords
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


def fetch_all_with_status(since: datetime, max_workers: int = DEFAULT_MAX_WORKERS) -> FetchAllResult:
    all_items: list[NewsItem] = []
    statuses: list[AgencyFetchStatus] = []
    scrapers = build_scrapers()
    workers = max(1, min(max_workers, len(scrapers)))
    print(f"[info] 使用 {workers} 個 worker 併發抓取 {len(scrapers)} 個機關")
    failed_scrapers: list[tuple[AgencyFeedScraper, str, float]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for scraper in scrapers:
            print(f"[info] 排入抓取 {scraper.agency.display_name}")
            future_map[executor.submit(scraper.fetch, since)] = (scraper, monotonic())

        for future in as_completed(future_map):
            scraper, started_at = future_map[future]
            duration = monotonic() - started_at
            try:
                items = future.result()
            except Exception as exc:
                print(f"[warn] 機關抓取失敗：{scraper.agency.display_name} ({exc})")
                failed_scrapers.append((scraper, str(exc), duration))
                continue
            print(f"[info] 完成 {scraper.agency.display_name}：{len(items)} 筆")
            statuses.append(
                AgencyFetchStatus(
                    agency_name=scraper.agency.display_name,
                    source_name=scraper.agency.short_name,
                    success=True,
                    item_count=len(items),
                    duration_seconds=duration,
                    newest_published_at=_newest_published_at(items),
                    warning=_health_warning(scraper.agency.short_name, items, since),
                )
            )
            all_items.extend(items)

    if failed_scrapers:
        print(f"[info] 有 {len(failed_scrapers)} 個機關未抓取成功，等待 {RETRY_DELAY_SECONDS} 秒後重新抓取")
        sleep(RETRY_DELAY_SECONDS)
        retry_workers = max(1, min(workers, len(failed_scrapers)))
        with ThreadPoolExecutor(max_workers=retry_workers) as executor:
            future_map = {
                executor.submit(scraper.fetch, since): (scraper, first_error, first_duration, monotonic())
                for scraper, first_error, first_duration in failed_scrapers
            }

            for future in as_completed(future_map):
                scraper, first_error, first_duration, started_at = future_map[future]
                duration = first_duration + (monotonic() - started_at)
                try:
                    items = future.result()
                except Exception as exc:
                    print(f"[warn] 重試仍失敗：{scraper.agency.display_name} ({exc})")
                    statuses.append(
                        AgencyFetchStatus(
                            agency_name=scraper.agency.display_name,
                            source_name=scraper.agency.short_name,
                            success=False,
                            attempts=2,
                            error=f"首次：{first_error}；重試：{exc}",
                            duration_seconds=duration,
                        )
                    )
                    continue
                print(f"[info] 重試完成 {scraper.agency.display_name}：{len(items)} 筆")
                statuses.append(
                    AgencyFetchStatus(
                        agency_name=scraper.agency.display_name,
                        source_name=scraper.agency.short_name,
                        success=True,
                        item_count=len(items),
                        attempts=2,
                        duration_seconds=duration,
                        newest_published_at=_newest_published_at(items),
                        warning=_health_warning(scraper.agency.short_name, items, since),
                    )
                )
                all_items.extend(items)

    return FetchAllResult(items=dedupe_items(all_items), statuses=statuses)


def fetch_all(since: datetime, max_workers: int = DEFAULT_MAX_WORKERS) -> list[NewsItem]:
    return fetch_all_with_status(since, max_workers=max_workers).items


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


def _health_warning(source_name: str, items: list[NewsItem], since: datetime) -> str:
    item_count = len(items)
    minimum = SOURCE_HEALTH_MIN_ITEMS.get(source_name, 0)
    if item_count < minimum:
        return f"{source_name} 筆數異常：取得 {item_count} 筆，低於健康門檻 {minimum} 筆"
    maximum_age_days = SOURCE_HEALTH_MAX_AGE_DAYS.get(source_name)
    now = datetime.now(timezone.utc)
    if (
        maximum_age_days is not None
        and items
        and since >= now - timedelta(days=30)
        and max(item.published_at for item in items) < now - timedelta(days=maximum_age_days)
    ):
        return f"{source_name} 最新資料已超過 {maximum_age_days} 天"
    return ""


def _newest_published_at(items: list[NewsItem]) -> str:
    if not items:
        return ""
    return max(item.published_at for item in items).isoformat()
