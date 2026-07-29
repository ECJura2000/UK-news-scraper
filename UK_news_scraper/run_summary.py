from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

from .models import NewsItem, ParliamentBriefing, RunStatus, SourceHealth


DATA_FINGERPRINT_VERSION = "v2"


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    generated_at: str
    period_start: str
    period_end: str
    output_file: str
    all_news_count: int
    filtered_news_count: int
    parliament_count: int
    filtered_parliament_count: int
    status: RunStatus
    warnings: tuple[str, ...]
    data_fingerprint: str
    delivery_id: str
    source_health: tuple[SourceHealth, ...]
    profile_id: str = "uk-tech-law"
    profile_name: str = "UK 科技法制"
    profile_version: int = 1
    profile_hash: str = ""
    selected_sources: tuple[str, ...] = ()
    minimum_score: int = 3
    excel_date_calendar: str = "gregorian"


def write_run_summary(summary: RunSummary, output_path: str | Path) -> Path:
    path = Path(output_path).with_suffix(".run.json")
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def validate_run_summary_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("run summary 必須是 JSON object")
    required = {
        "delivery_id",
        "run_id",
        "status",
        "data_fingerprint",
        "output_file",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"run summary 缺少欄位：{sorted(missing)}")
    RunStatus(payload["status"])
    if not all(isinstance(payload[key], str) and payload[key] for key in required):
        raise ValueError("run summary 必要欄位必須是非空字串")
    return payload


def make_run_id(period_start: date, period_end: date) -> str:
    return f"uk-news-{period_start.isoformat()}_{period_end.isoformat()}"


def make_data_fingerprint(
    news_items: list[NewsItem],
    parliament_items: list[ParliamentBriefing],
) -> str:
    records = [
        {
            "type": "news",
            "agency": item.agency,
            "agency_en": item.agency_en,
            "unit_category": item.unit_category,
            "date": item.date_text,
            "title": item.title,
            "summary": item.summary,
            "link": item.link,
            "source_feed": item.source_feed,
            "matched_topics": sorted(item.matched_topics),
            "matched_keywords": sorted(item.matched_keywords, key=str.casefold),
            "core_matched_keywords": sorted(item.core_matched_keywords, key=str.casefold),
            "general_matched_keywords": sorted(item.general_matched_keywords, key=str.casefold),
            "supporting_matched_keywords": sorted(item.supporting_matched_keywords, key=str.casefold),
            "relevance_score": item.relevance_score,
        }
        for item in news_items
    ]
    records.extend(
        {
            "type": "parliament",
            "publisher": item.publisher,
            "chamber": item.chamber,
            "date": item.date_text,
            "identifier": item.identifier,
            "document_type": item.document_type,
            "title": item.title,
            "summary": item.summary,
            "webpage_url": item.webpage_url,
            "pdf_url": item.pdf_url,
            "fetched_from": item.fetched_from,
            "topics": sorted(item.topics),
            "matched_topics": sorted(item.matched_topics),
            "matched_keywords": sorted(item.matched_keywords, key=str.casefold),
            "core_matched_keywords": sorted(item.core_matched_keywords, key=str.casefold),
            "general_matched_keywords": sorted(item.general_matched_keywords, key=str.casefold),
            "supporting_matched_keywords": sorted(item.supporting_matched_keywords, key=str.casefold),
            "relevance_score": item.relevance_score,
        }
        for item in parliament_items
    )
    records.sort(
        key=lambda record: json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    payload = json.dumps(
        {"schema": DATA_FINGERPRINT_VERSION, "records": records},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_delivery_id(run_id: str, status: str, data_fingerprint: str) -> str:
    return f"{run_id}:{status}:{data_fingerprint[:16]}"
