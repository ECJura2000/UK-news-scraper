"""Plan removal of duplicate publication channels while preserving audit evidence.

The default writes only a local removal plan. --apply adopts that plan and keeps
reversible exclusions in the reviewed source state, never discarding source rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.audit_source_catalog import write_json  # noqa: E402
from UK_news_scraper.config import AGENCIES  # noqa: E402
from UK_news_scraper.source_review import apply_review_state  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "UK_news_scraper/data/source_catalog.json"
OVERRIDES = CATALOG.with_name("source_catalog_overrides.json")
MEXE = "govuk:military-engineering-experimental-establishment"
# Separate, body-scoped indexes were identified during the second review.
KEEP_SCOPED_CHANNELS = {
    "govuk:research-england", "scotland:accounts-commission-for-scotland",
    "scotland:scottish-courts-and-tribunals-service",
}


def plan_removals(sources: list[dict], audit_rows: list[dict], checked_at: str, extra_ids: set[str]) -> list[dict]:
    entries = {row["id"]: row for row in sources}
    available = {row["id"] for row in sources if row["status"] == "searchable"} | extra_ids
    removals = []
    for row in audit_rows:
        original = entries.get(row["id"])
        if not original or original["status"] == "searchable" or row["id"] in KEEP_SCOPED_CHANNELS:
            continue
        outcome = row["outcome"]
        replacements = row.get("parent_sources", []) or row.get("alternative_sources", [])
        reason = row.get("reason", "")
        evidence_url = original.get("authority_url") or original.get("provenance") or original["homepage"]
        if outcome in {"covered_by_parent", "available_as_other_source"}:
            if not replacements or not set(replacements) <= available:
                raise ValueError(f"刪除來源未找到仍可查詢的替代管道：{row['id']}")
            if outcome == "covered_by_parent":
                reason = "共用採集路由，移至既有發布來源；保留機關與替代路由對照（不表示機關裁撤）：" + reason
        elif outcome == "policy_excluded" and row["id"] == "govuk:bbc":
            replacements = []
        elif row["id"] == MEXE and outcome == "feed_validation_failed":
            outcome = "obsolete_source"
            reason = "舊政府機關網址現為獨立非營利公司；不屬現行政府發布來源，唯一 RSS 為 WordPress 樣板"
            evidence_url = "https://mexe.org.uk/"
        else:
            continue
        removals.append({
            "id": row["id"], "outcome": outcome, "reason": reason, "checked_at": checked_at,
            "authority_url": evidence_url, "replacement_sources": replacements,
            "original_source": original,
        })
    return sorted(removals, key=lambda row: row["id"])


def plan_disabled_removals(sources: list[dict], checked_at: str) -> list[dict]:
    """Explicit user choice removes disabled rows without judging their agencies."""
    return [{
        "id": source["id"], "outcome": "user_requested_removal",
        "reason": "依使用者明確指示移除僅列名項目；原機關狀態、查核原因與來源資料保留於備份",
        "checked_at": checked_at,
        "authority_url": source.get("authority_url") or source.get("provenance") or source["homepage"],
        "replacement_sources": source.get("parent_sources", []) or source.get("alternative_sources", []),
        "original_status": source["status"], "original_reason": source.get("reason", ""),
        "original_source": source,
    } for source in sources if source["status"] == "directory_only"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=ROOT / "新聞放置區/source-audit/audit.json")
    parser.add_argument("--plan", type=Path, default=ROOT / "新聞放置區/source-audit/cleanup-removals.json")
    parser.add_argument("--apply", action="store_true", help="採用已產生的刪除計畫並保存可復原紀錄")
    parser.add_argument("--remove-disabled", action="store_true", help="依使用者明確指示，計畫移除全部僅列名來源")
    args = parser.parse_args()
    if args.apply and args.remove_disabled:
        parser.error("請先使用 --remove-disabled 產生可檢閱計畫，再以 --apply 採用")
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    state = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    if args.apply:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if plan.get("schema_version") != 1 or not isinstance(plan.get("exclusions"), list):
            raise ValueError("不支援的來源刪除計畫")
        exclusions = {item["id"]: item for item in state.get("exclusions", [])}
        current = {item["id"]: item for item in catalog["sources"]}
        for item in plan["exclusions"]:
            # Reapplying the same plan must not replace the original recovery row.
            if item["id"] not in exclusions and current.get(item["id"]) != item.get("original_source"):
                raise ValueError(f"來源已變更，請重新產生刪除計畫：{item['id']}")
            exclusions.setdefault(item["id"], item)
        state["exclusions"] = sorted(exclusions.values(), key=lambda item: item["id"])
        catalog["sources"] = apply_review_state(
            catalog["sources"], state.get("reviews", []), state.get("assessments", []), state["exclusions"],
        )
        write_json(OVERRIDES, state)
        write_json(CATALOG, catalog)
        print(f"excluded={len(state['exclusions'])}; active_sources={len(catalog['sources'])}")
    else:
        if args.remove_disabled:
            # Keep complete pre-removal snapshots in addition to row-level
            # tombstones. Repeated planning cannot overwrite the first backup.
            for path, payload in (
                (args.plan.with_suffix(".catalog-before-removal.json"), catalog),
                (args.plan.with_suffix(".overrides-before-removal.json"), state),
            ):
                if not path.exists():
                    write_json(path, payload)
            new_removals = plan_disabled_removals(catalog["sources"], datetime.now(UTC).isoformat())
        else:
            audit = json.loads(args.audit.read_text(encoding="utf-8"))
            new_removals = plan_removals(
                catalog["sources"], audit["sources"], datetime.now(UTC).isoformat(),
                {agency.short_name for agency in AGENCIES},
            )
        retained = {item["id"]: item for item in state.get("exclusions", [])}
        for item in new_removals:
            retained.setdefault(item["id"], item)
        removals = sorted(retained.values(), key=lambda item: item["id"])
        write_json(args.plan, {"schema_version": 1, "exclusions": removals})
        print(f"planned_removals={len(removals)}; plan={args.plan}")


if __name__ == "__main__":
    main()
