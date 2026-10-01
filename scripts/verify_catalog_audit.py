"""Verify saved endpoint bodies with production Python/Rust parsers before adoption."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import feedparser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.audit_source_catalog import SINCE, normalized, same_site, write_json  # noqa: E402
from UK_news_scraper.catalog_html import parse_news_index  # noqa: E402
from UK_news_scraper.models import Agency  # noqa: E402
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper  # noqa: E402
from UK_news_scraper.source_catalog import GOVUK_LINKS  # noqa: E402


def canonical(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        row = dict(item)
        row["published_at"] = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00")).astimezone(
            UTC
        ).isoformat(timespec="microseconds")
        normalized.append(row)
    return sorted(normalized, key=lambda x: (x["link"], x["published_at"], x["title"]))


def alias_scope_matches(source: dict, candidate: dict) -> bool:
    if source["jurisdiction"] == candidate["jurisdiction"]:
        return True
    markers = {
        "Northern Ireland": ("northern ireland",), "Scotland": ("scotland", "scottish"),
        "Wales": ("wales", "welsh"),
    }
    name = normalized(source["name_en"])
    return candidate["jurisdiction"] == "UK" and any(
        marker in name for marker in markers.get(source["jurisdiction"], ())
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "新聞放置區/source-audit")
    args = parser.parse_args()
    audit_path = args.output_dir / "audit.json"
    audit = json.loads(audit_path.read_text())
    sources = {x["id"]: x for x in json.loads((args.output_dir / "baseline.json").read_text())["sources"]}
    until = datetime.fromisoformat(audit["completed_at"])
    bundles, python_results, checks = [], {}, {}
    for row in audit["sources"]:
        if row["outcome"] not in {"verified", "parser_verification_failed"}:
            continue
        review = row["review"]
        source = sources[row["id"]]
        endpoint = review["endpoint"]
        key = hashlib.sha256(endpoint.encode()).hexdigest()
        body_path = args.output_dir / "http" / f"{key}.body"
        body = body_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != review["verification"]["response_sha256"]:
            raise ValueError(f"HTTP 證據雜湊不一致：{row['id']}")
        agency = Agency(source["name_zh"] or source["name_en"], source["name_en"], row["id"], review["homepage"],
                        link_include_patterns=GOVUK_LINKS if review["adapter"] == "govuk_search" else ())
        scraper = AgencyFeedScraper(agency, until)
        if review["adapter"] == "govuk_search":
            payload = json.loads(body)

            def page(url, payload=payload):
                start = parse_qs(urlparse(url).query).get("start", ["0"])[0]
                return payload if start == "0" else {"results": [], "total": len(payload["results"])}

            with patch("UK_news_scraper.scrapers.ministry.registry.get_json", page):
                items = scraper._fetch_govuk_search(SINCE)
        elif review["adapter"] == "feed":
            items = [item for value in feedparser.parse(body).entries
                     if (item := scraper._entry_to_news_item(value, endpoint, SINCE))
                     and same_site(item.link, agency.homepage)]
        else:
            items = parse_news_index(body.decode("utf-8", errors="replace"), agency, endpoint, SINCE, until)
        python_results[row["id"]] = canonical([
            {"title": x.title, "link": x.link, "published_at": x.published_at.isoformat(),
             "content_type": x.content_type, "summary": x.summary} for x in items
        ])
        if review["adapter"] != "govuk_search":
            bundles.append({**review, "name_en": source["name_en"], "name_zh": source["name_zh"] or source["name_en"],
                            "body_path": str(body_path.resolve())})
        else:
            checks[row["id"]] = {"passed": bool(items), "python_count": len(items),
                                 "adapter": "existing GOV.UK Search; replayed production Python parser"}
    bundle_path = args.output_dir / "replay_bundle.json"
    write_json(bundle_path, {"until": until.isoformat(), "sources": bundles})
    result = subprocess.run(
        ["cargo", "run", "--locked", "-q", "-p", "uk-news-sources", "--example", "verify_catalog_endpoints", "--",
         str(bundle_path.resolve())], cwd=ROOT, text=True, capture_output=True, check=True,
    )
    rust_results = json.loads(result.stdout)
    write_json(args.output_dir / "rust_replay.json", rust_results)
    for row in rust_results:
        identifier = row["id"]
        expected = python_results[identifier]
        actual = canonical(row["items"])
        checks[identifier] = {"passed": bool(expected) and expected == actual and not row.get("error"),
                              "python_count": len(expected), "rust_count": len(actual),
                              "python_items": expected, "rust_items": actual, "error": row.get("error", "")}
    for row in audit["sources"]:
        if row["outcome"] not in {"verified", "parser_verification_failed"}:
            continue
        checked = checks[row["id"]]
        if checked["passed"]:
            row["outcome"] = "verified"
            row["reason"] = "官方端點已通過生產解析器驗證"
            row["review"]["verification"].update(
                production_parser_verified=True,
                python_rust_parity=True if row["review"]["adapter"] != "govuk_search" else None,
                replay_count=checked["python_count"],
            )
        else:
            row["outcome"] = "parser_verification_failed"
            row["reason"] = "已找到官方端點，但 Python/Rust 生產解析器結果不一致或未解析到資料"
            row["review"]["verification"].update(production_parser_verified=False, python_rust_parity=False)
        path = args.output_dir / "sources" / f"{hashlib.sha256(row['id'].encode()).hexdigest()}.json"
        write_json(path, row)
    queryable = {}
    for source in sources.values():
        if source["status"] == "searchable":
            queryable.setdefault(normalized(source["name_en"]), []).append(source["id"])
    for row in audit["sources"]:
        if row["outcome"] == "verified":
            queryable.setdefault(normalized(row["name_en"]), []).append(row["id"])
    for row in audit["sources"]:
        if row["outcome"] in {"verified", "covered_by_parent", "permission_required", "policy_excluded"}:
            continue
        alternatives = sorted(
            identifier for identifier in set(queryable.get(normalized(row["name_en"]), []))
            if identifier != row["id"] and alias_scope_matches(sources[row["id"]], sources[identifier])
        )
        if len(alternatives) == 1:
            row.setdefault("original_outcome", row["outcome"])
            row.update(outcome="available_as_other_source",
                       reason=f"同名機關已有可查詢管道，請使用來源 ID：{alternatives[0]}",
                       alternative_sources=alternatives)
            path = args.output_dir / "sources" / f"{hashlib.sha256(row['id'].encode()).hexdigest()}.json"
            write_json(path, row)
    from collections import Counter

    audit["outcomes"] = dict(Counter(x["outcome"] for x in audit["sources"]))
    write_json(audit_path, audit)
    write_json(args.output_dir / "parser_verification.json", checks)
    print(json.dumps({"sources_checked": len(checks), "passed": sum(x["passed"] for x in checks.values()),
                      "failed": [k for k, v in checks.items() if not v["passed"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
