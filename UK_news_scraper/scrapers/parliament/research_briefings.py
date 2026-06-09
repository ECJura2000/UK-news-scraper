from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import html
import json
import os
import re
from typing import Any
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from ...http.async_client import get_json, get_text
from ...models import ParliamentBriefing
from ...rss import parse_feed
from ..ministry.utils.date import parse_datetime_text, parse_feed_datetime
from ..ministry.utils.text import clean_text


BASE_URL = "https://lda.data.parliament.uk/researchbriefings.json"
LORDS_SCIENCE_TECHNOLOGY_URL = (
    "https://lordslibrary.parliament.uk/topic/"
    "science-environment/science-environment-science-technology/"
)
TOPIC_ARCHIVE_SOURCES = (
    (
        "House of Lords Library Science & Technology",
        LORDS_SCIENCE_TECHNOLOGY_URL,
        "House of Lords",
        "House of Lords Library",
    ),
    (
        "House of Commons Library Technology",
        "https://commonslibrary.parliament.uk/topic/science/technology/",
        "House of Commons",
        "House of Commons Library",
    ),
    (
        "House of Commons Library Sciences",
        "https://commonslibrary.parliament.uk/topic/science/sciences/",
        "House of Commons",
        "House of Commons Library",
    ),
)
RSS_SOURCES = {
    "House of Commons Library": "https://commonslibrary.parliament.uk/research-briefings/feed/",
    "House of Lords Library": "https://lordslibrary.parliament.uk/research-briefings/feed/",
    "Parliamentary Office of Science and Technology": "https://post.parliament.uk/feed/",
}
CHAMBERS = {
    "House of Commons Library": "House of Commons",
    "House of Lords Library": "House of Lords",
    "Parliamentary Office of Science and Technology": "POST",
}
ID_RE = re.compile(r"\b(?:CBP|SN|LLN|POST-PN|POSTNOTE|POSTBRIEF)-?\d+\b", re.IGNORECASE)
PDF_RE = re.compile(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]*)?", re.IGNORECASE)


@dataclass
class ParliamentFetchResult:
    items: list[ParliamentBriefing]
    source_mode: str
    warnings: list[str] = field(default_factory=list)
    successful_sources: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)

    @property
    def all_successful(self) -> bool:
        return not self.failed_sources

    @property
    def has_usable_data(self) -> bool:
        return bool(self.items)


def fetch_parliament_briefings(
    since: datetime,
    page_size: int = 500,
    max_pages: int = 20,
) -> ParliamentFetchResult:
    warnings: list[str] = []
    successful_sources: list[str] = []
    failed_sources: list[str] = []
    if os.environ.get("UK_PARLIAMENT_TRY_API") == "1":
        try:
            items = _fetch_api(since, page_size=page_size, max_pages=max_pages)
            if not items:
                raise RuntimeError("API 未回傳指定期間內的 research briefings")
            print(f"[info] UK Parliament Research Briefings API：{len(items)} 筆")
            successful_sources.append("Research Briefings API")
            _extend_with_topic_archives(
                items, since, warnings, successful_sources, failed_sources
            )
            return ParliamentFetchResult(
                items=_dedupe(items),
                source_mode="Research Briefings API + official topic archives",
                warnings=warnings,
                successful_sources=successful_sources,
                failed_sources=failed_sources,
            )
        except Exception as exc:
            warning = f"Research Briefings API 無法使用，改抓官方 RSS：{exc}"
            warnings.append(warning)
            failed_sources.append("Research Briefings API")
            print(f"[warn] {warning}")
    else:
        print("[info] UK Parliament Research Briefings：使用官方 RSS（API 健康檢查已停用）")

    items: list[ParliamentBriefing] = []
    for publisher, feed_url in RSS_SOURCES.items():
        try:
            feed_items = _fetch_rss(publisher, feed_url, since)
        except Exception as exc:
            warning = f"{publisher} RSS 讀取失敗：{exc}"
            warnings.append(warning)
            failed_sources.append(f"{publisher} RSS")
            print(f"[warn] {warning}")
            continue
        print(f"[info] {publisher} RSS：{len(feed_items)} 筆")
        successful_sources.append(f"{publisher} RSS")
        items.extend(feed_items)
    _extend_with_topic_archives(
        items, since, warnings, successful_sources, failed_sources
    )
    return ParliamentFetchResult(
        items=_dedupe(items),
        source_mode="Official RSS + official topic archives",
        warnings=warnings,
        successful_sources=successful_sources,
        failed_sources=failed_sources,
    )


def _extend_with_topic_archives(
    items: list[ParliamentBriefing],
    since: datetime,
    warnings: list[str],
    successful_sources: list[str],
    failed_sources: list[str],
) -> None:
    for label, archive_url, chamber, publisher in TOPIC_ARCHIVE_SOURCES:
        try:
            topic_items = _fetch_topic_archive(
                since,
                archive_url=archive_url,
                chamber=chamber,
                publisher=publisher,
            )
        except Exception as exc:
            warning = f"{label} 主題頁讀取失敗：{exc}"
            warnings.append(warning)
            failed_sources.append(f"{label} topic archive")
            print(f"[warn] {warning}")
            continue
        print(f"[info] {label} 主題頁：{len(topic_items)} 筆")
        successful_sources.append(f"{label} topic archive")
        items.extend(topic_items)


def _fetch_api(since: datetime, page_size: int, max_pages: int) -> list[ParliamentBriefing]:
    items: list[ParliamentBriefing] = []
    for page in range(max_pages):
        params = urlencode({"_view": "all", "_page": page, "_pageSize": page_size, "_sort": "-date"})
        payload = get_json(f"{BASE_URL}?{params}", timeout=5)
        page_items = payload.get("result", {}).get("items", [])
        if not isinstance(page_items, list):
            raise ValueError("API result.items 格式異常")
        parsed = [_parse_api_item(item) for item in page_items]
        items.extend(item for item in parsed if item and item.published_at >= since)
        dates = [item.published_at for item in parsed if item]
        if len(page_items) < page_size or (dates and min(dates) < since):
            break
    return items


def _parse_api_item(item: dict[str, Any]) -> ParliamentBriefing | None:
    publisher = _first_text(item, "publisher", "publisher.prefLabel", "publisher_label")
    published_at = parse_datetime_text(_first_text(item, "date", "published", "publicationDate"))
    title = _first_text(item, "title", "label")
    webpage_url = _first_text(item, "_about", "url", "webpage", "uri")
    if not publisher or not published_at or not title:
        return None
    return ParliamentBriefing(
        published_at=published_at,
        chamber=CHAMBERS.get(publisher, ""),
        publisher=publisher,
        title=title,
        summary=_first_text(item, "abstract", "description", "summary"),
        identifier=_first_text(item, "identifier", "id") or _identifier(webpage_url, title),
        webpage_url=webpage_url,
        pdf_url=_first_text(item, "pdf", "pdfUrl", "attachment", "document"),
        topics=_list_text(item.get("topic") or item.get("topics") or item.get("topic.prefLabel")),
        document_type=_first_text(item, "type", "publicationType") or "Research Briefing",
        fetched_from="Research Briefings API",
    )


def _fetch_rss(publisher: str, feed_url: str, since: datetime) -> list[ParliamentBriefing]:
    feed = parse_feed(feed_url)
    items: list[ParliamentBriefing] = []
    for entry in feed.entries:
        published_at = parse_feed_datetime(entry)
        if not published_at or published_at < since:
            continue
        title = clean_text(str(getattr(entry, "title", "")))
        webpage_url = str(getattr(entry, "link", ""))
        content = _entry_content(entry)
        identifier = _identifier(webpage_url, str(getattr(entry, "id", "")), title)
        pdf_url = _pdf_url(content, identifier)
        if not pdf_url and identifier.startswith(("CBP-", "SN-")):
            pdf_url = f"https://researchbriefings.files.parliament.uk/documents/{identifier}/{identifier}.pdf"
        items.append(
            ParliamentBriefing(
                published_at=published_at,
                chamber=CHAMBERS[publisher],
                publisher=publisher,
                title=title,
                summary=clean_text(str(getattr(entry, "summary", ""))),
                identifier=identifier,
                webpage_url=webpage_url,
                pdf_url=pdf_url,
                topics=_rss_topics(entry),
                fetched_from=f"Official RSS: {feed_url}",
            )
        )
    return items


def _fetch_lords_science_technology_archive(
    since: datetime,
    max_pages: int = 20,
) -> list[ParliamentBriefing]:
    return _fetch_topic_archive(
        since,
        archive_url=LORDS_SCIENCE_TECHNOLOGY_URL,
        chamber="House of Lords",
        publisher="House of Lords Library",
        max_pages=max_pages,
    )


def _fetch_topic_archive(
    since: datetime,
    archive_url: str,
    chamber: str,
    publisher: str,
    max_pages: int = 20,
) -> list[ParliamentBriefing]:
    items: list[ParliamentBriefing] = []
    for page in range(1, max_pages + 1):
        page_url = (
            archive_url
            if page == 1
            else urljoin(archive_url, f"page/{page}/")
        )
        soup = BeautifulSoup(get_text(page_url), "html.parser")
        page_items = [
            item
            for article in soup.select("article.card")
            if (
                item := _parse_topic_article(
                    article,
                    page_url=page_url,
                    archive_url=archive_url,
                    chamber=chamber,
                    publisher=publisher,
                )
            )
        ]
        if not page_items:
            break
        items.extend(item for item in page_items if item.published_at >= since)
        if min(item.published_at for item in page_items) < since:
            break
    return items


def _parse_topic_article(
    article,
    page_url: str,
    archive_url: str,
    chamber: str,
    publisher: str,
) -> ParliamentBriefing | None:
    title_link = article.select_one(".card__heading a[href]")
    time_tag = article.select_one("time[datetime]")
    if not title_link or not time_tag:
        return None
    published_at = parse_datetime_text(str(time_tag.get("datetime", "")))
    title = clean_text(title_link.get_text(" ", strip=True))
    webpage_url = urljoin(page_url, str(title_link.get("href", "")))
    if not published_at or not title or not webpage_url:
        return None
    tags = [
        clean_text(link.get_text(" ", strip=True))
        for link in article.select(".tag-list a[href]")
    ]
    type_tags = [
        clean_text(link.get_text(" ", strip=True))
        for link in article.select('.tag-list a[href*="/type/"]')
    ]
    summary_tag = article.select_one(".card__date + p")
    identifier = _identifier(webpage_url, title)
    pdf_url = ""
    if identifier.startswith(("CBP-", "SN-")):
        pdf_url = f"https://researchbriefings.files.parliament.uk/documents/{identifier}/{identifier}.pdf"
    return ParliamentBriefing(
        published_at=published_at,
        chamber=chamber,
        publisher=publisher,
        title=title,
        summary=clean_text(summary_tag.get_text(" ", strip=True)) if summary_tag else "",
        identifier=identifier,
        webpage_url=webpage_url,
        pdf_url=pdf_url,
        topics=[topic for topic in tags if topic not in type_tags],
        document_type=type_tags[0] if type_tags else "Research Briefing",
        fetched_from=f"Official topic archive: {archive_url}",
    )


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        values = _list_text(value)
        if values:
            return values[0]
    return ""


def _list_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        output: list[str] = []
        for part in value:
            output.extend(_list_text(part))
        return list(dict.fromkeys(filter(None, output)))
    if isinstance(value, dict):
        for key in ("_value", "prefLabel", "label", "title", "name"):
            if value.get(key):
                return _list_text(value[key])
        return []
    normalized = clean_text(html.unescape(str(value)))
    return [normalized] if normalized else []


def _rss_topics(entry: Any) -> list[str]:
    topics: list[str] = []
    for tag in getattr(entry, "tags", []) or []:
        topic = clean_text(str(tag.get("term", "")))
        if topic:
            topics.append(topic)
    return list(dict.fromkeys(topics))


def _entry_content(entry: Any) -> str:
    content = getattr(entry, "content", "") or ""
    if isinstance(content, list):
        return " ".join(str(part.get("value", part)) for part in content)
    return str(content)


def _identifier(*values: str) -> str:
    combined = " ".join(values)
    match = ID_RE.search(combined)
    if match:
        return match.group(0).upper()
    slug = re.search(r"/(?:research-briefings/)?((?:cbp|sn|lln|post-pn)-\d+)/?", combined, re.IGNORECASE)
    return slug.group(1).upper() if slug else ""


def _pdf_url(content: str, identifier: str) -> str:
    if not identifier:
        return ""
    for match in PDF_RE.finditer(html.unescape(content)):
        if identifier.casefold() in match.group(0).casefold():
            return match.group(0)
    return ""


def _dedupe(items: list[ParliamentBriefing]) -> list[ParliamentBriefing]:
    seen: set[str] = set()
    output: list[ParliamentBriefing] = []
    for item in sorted(items, key=lambda briefing: briefing.published_at, reverse=True):
        key = item.identifier or item.webpage_url.rstrip("/") or f"{item.publisher}:{item.title}"
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
