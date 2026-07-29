from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Iterable

from .config import AGENCIES
from .profiles import PARLIAMENT_SOURCE_ID
from .run_summary import validate_run_summary_payload


ResultRow = tuple[str, Any]


@dataclass(frozen=True)
class ResultFilters:
    query: str = ""
    item_type: str = "全部"
    strength: str = "全部強度"
    source: str = "全部來源"
    topic: str = "全部主題"
    minimum_score: int = 0
    maximum_score: int = 999
    date_start: date | None = None
    date_end: date | None = None


@dataclass(frozen=True)
class RunHistoryEntry:
    summary_path: Path
    workbook_path: Path
    generated_at: datetime
    period_start: date
    period_end: date
    status: str
    profile_name: str
    all_news_count: int
    filtered_news_count: int
    parliament_count: int


def filter_and_sort_results(
    rows: Iterable[ResultRow],
    filters: ResultFilters,
    *,
    sort_column: str = "score",
    descending: bool = True,
) -> list[ResultRow]:
    query = filters.query.casefold().strip()
    filtered: list[ResultRow] = []
    for item_type, item in rows:
        source = item_source(item_type, item)
        published_date = item.published_at.date()
        if filters.item_type != "全部" and filters.item_type != item_type:
            continue
        searchable = (
            f"{item.title} {item.summary} {' '.join(item.matched_topics)} "
            f"{' '.join(item.matched_keywords)} {source}"
        ).casefold()
        if query and query not in searchable:
            continue
        strength_matches = {
            "核心": bool(item.core_matched_keywords),
            "一般": bool(item.general_matched_keywords),
            "輔助": bool(item.supporting_matched_keywords),
        }
        if filters.strength != "全部強度" and not strength_matches[filters.strength]:
            continue
        if filters.source != "全部來源" and filters.source != source:
            continue
        if filters.topic != "全部主題" and filters.topic not in item.matched_topics:
            continue
        if not filters.minimum_score <= item.relevance_score <= filters.maximum_score:
            continue
        if filters.date_start and published_date < filters.date_start:
            continue
        if filters.date_end and published_date > filters.date_end:
            continue
        filtered.append((item_type, item))
    return sorted(
        filtered,
        key=lambda row: result_sort_value(row, sort_column),
        reverse=descending,
    )


def result_sort_value(row: ResultRow, column: str):
    item_type, item = row
    values = {
        "type": item_type.casefold(),
        "date": item.published_at,
        "source": item_source(item_type, item).casefold(),
        "score": item.relevance_score,
        "level": {"高": 3, "中": 2, "低": 1}.get(item.relevance_level, 0),
        "title": item.title.casefold(),
    }
    return values.get(column, item.relevance_score)


def item_source(item_type: str, item: Any) -> str:
    return item.agency if item_type == "新聞" else item.publisher


def failed_source_ids(source_health: Iterable[Any]) -> tuple[str, ...]:
    agency_ids = {agency.short_name for agency in AGENCIES}
    failed: set[str] = set()
    for health in source_health:
        if health.success and not health.warning:
            continue
        if health.source in agency_ids:
            failed.add(health.source)
        else:
            failed.add(PARLIAMENT_SOURCE_ID)
    source_order = [agency.short_name for agency in AGENCIES] + [PARLIAMENT_SOURCE_ID]
    return tuple(source for source in source_order if source in failed)


def load_run_history(output_dir: str | Path, limit: int = 30) -> list[RunHistoryEntry]:
    directory = Path(output_dir).expanduser()
    if not directory.is_dir():
        return []
    entries: list[RunHistoryEntry] = []
    summaries = sorted(
        directory.glob("*.run.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in summaries:
        try:
            payload = validate_run_summary_payload(
                json.loads(path.read_text(encoding="utf-8"))
            )
            entry = _history_entry(path, payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break
    return entries


def _history_entry(summary_path: Path, payload: dict) -> RunHistoryEntry:
    generated_at = datetime.fromisoformat(str(payload.get("generated_at", "")))
    workbook_path = Path(str(payload["output_file"])).expanduser()
    return RunHistoryEntry(
        summary_path=summary_path.resolve(),
        workbook_path=workbook_path.resolve(),
        generated_at=generated_at,
        period_start=date.fromisoformat(str(payload["period_start"])),
        period_end=date.fromisoformat(str(payload["period_end"])),
        status=str(payload["status"]),
        profile_name=str(payload.get("profile_name", payload.get("profile_id", ""))),
        all_news_count=int(payload.get("all_news_count", 0)),
        filtered_news_count=int(payload.get("filtered_news_count", 0)),
        parliament_count=int(payload.get("parliament_count", 0)),
    )
