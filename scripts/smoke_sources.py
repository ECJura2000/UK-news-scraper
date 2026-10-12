from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from UK_news_scraper.article_links import is_agency_homepage
from UK_news_scraper.config import AGENCIES, DEFAULT_FETCH_BUDGET_SECONDS
from UK_news_scraper.http.async_client import request_deadline
from UK_news_scraper.profiles import default_profile
from UK_news_scraper.scrapers.ministry.registry import fetch_all_with_status
from UK_news_scraper.scrapers.parliament import fetch_parliament_briefings

WEEKLY_AGENCIES = tuple(agency for agency in AGENCIES if agency.short_name in default_profile().selected_sources)

# Retained for integrations that import the old endpoint inventory.
SOURCES = {agency.short_name: agency.homepage for agency in WEEKLY_AGENCIES}
SOURCES["GOV.UK"] = "https://www.gov.uk/search/news-and-communications"
SOURCES["UK Parliament"] = "https://commonslibrary.parliament.uk/feed/"


def valid_record(item, since: datetime, until: datetime) -> bool:
    link = getattr(item, "link", getattr(item, "webpage_url", ""))
    try:
        parsed = urlsplit(link)
    except ValueError:
        return False
    return bool(
        item.title.strip()
        and parsed.scheme in {"https", "http"}
        and parsed.hostname
        and item.published_at.tzinfo
        and since <= item.published_at < until
        and not is_agency_homepage(link)
    )


def valid_agency_link(item, agency) -> bool:
    host = (urlsplit(item.link).hostname or "").lower().removeprefix("www.")
    feed_host = (urlsplit(item.source_feed).hostname or "").lower()
    if host == "news.google.com":
        return feed_host == "news.google.com"  # Publisher is verified by the production fallback parser.
    domains = [
        (urlsplit(url).hostname or "").lower().removeprefix("www.")
        for url in (agency.homepage, *agency.news_pages, *agency.official_pages)
    ]
    return bool(host) and any(domain and (host == domain or host.endswith("." + domain)) for domain in domains)


def inspect_results(agency_result, parliament_result, since, until) -> dict:
    issues = []
    health = list(agency_result.source_health) + list(parliament_result.source_health)
    for source in health:
        if not source.success:
            issues.append({"source": source.source, "kind": "fetch_failed", "message": source.warning})
        elif source.candidate_count > 0 and source.item_count == 0:
            issues.append({"source": source.source, "kind": "parser_empty", "message": source.warning})
        elif any(word in source.warning for word in ("解析為零", "未解析到", "解析失敗", "欄位不完整")):
            issues.append({"source": source.source, "kind": "parser_warning", "message": source.warning})
    known_agencies = {agency.display_name: agency for agency in WEEKLY_AGENCIES}
    for item in agency_result.items:
        agency = known_agencies.get(item.agency)
        if (
            not valid_record(item, since, until)
            or agency is None
            or item.agency_en != agency.name_en
            or not valid_agency_link(item, agency)
        ):
            issues.append({"source": item.agency, "kind": "invalid_record", "message": item.title})
    for item in parliament_result.items:
        valid = valid_record(item, since, until)
        host = (urlsplit(item.webpage_url).hostname or "").lower() if valid else ""
        if not valid or not (host == "parliament.uk" or host.endswith(".parliament.uk")):
            issues.append({"source": item.publisher, "kind": "invalid_record", "message": item.title})
    if not health:
        issues.append({"source": "all", "kind": "missing_health", "message": "沒有來源健康紀錄"})
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "period_start": since.isoformat(),
        "period_end_exclusive": until.isoformat(),
        "ok": not issues,
        "issues": issues,
        "source_health": [asdict(source) for source in health],
        "agency_count": len(agency_result.items),
        "parliament_count": len(parliament_result.items),
        "scope": "built-in weekly sources; production parsers and attribution rules",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check production source parsing without export or delivery.")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.days <= 90:
        parser.error("--days 必須介於 1 與 90，避免每日檢查大量歷史資料")
    until = datetime.now(UTC)
    since = until - timedelta(days=args.days)
    agencies = fetch_all_with_status(since, until=until, agencies=WEEKLY_AGENCIES)
    with request_deadline(monotonic() + DEFAULT_FETCH_BUDGET_SECONDS):
        parliament = fetch_parliament_briefings(since)
    parliament.items = [item for item in parliament.items if item.published_at < until]
    result = inspect_results(agencies, parliament, since, until)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for issue in result["issues"]:
        print(f"::warning::{issue['source']}: {issue['kind']}")
    print(f"production source check: {len(result['source_health'])} routes; ok={result['ok']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
