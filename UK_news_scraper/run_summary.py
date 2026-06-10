from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

from .models import NewsItem, ParliamentBriefing, SourceHealth


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
    status: str
    warnings: tuple[str, ...]
    data_fingerprint: str
    delivery_id: str
    source_health: tuple[SourceHealth, ...]


def write_run_summary(summary: RunSummary, output_path: str | Path) -> Path:
    path = Path(output_path).with_suffix(".run.json")
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


def make_run_id(period_start: date, period_end: date) -> str:
    return f"uk-news-{period_start.isoformat()}_{period_end.isoformat()}"


def make_data_fingerprint(
    news_items: list[NewsItem],
    parliament_items: list[ParliamentBriefing],
) -> str:
    records = [f"schema|{DATA_FINGERPRINT_VERSION}"]
    records.extend(
        "|".join(
            (
                "news",
                item.agency,
                item.agency_en,
                item.unit_category or "",
                item.date_text,
                item.title,
                item.summary,
                item.link,
                item.source_feed,
                ",".join(sorted(item.matched_topics)),
                ",".join(sorted(item.matched_keywords, key=str.casefold)),
            )
        )
        for item in news_items
    )
    records.extend(
        "|".join(
            (
                "parliament",
                item.publisher,
                item.chamber,
                item.date_text,
                item.identifier,
                item.document_type,
                item.title,
                item.summary,
                item.webpage_url,
                item.pdf_url,
                item.fetched_from,
                ",".join(sorted(item.topics)),
                ",".join(sorted(item.matched_topics)),
                ",".join(sorted(item.matched_keywords, key=str.casefold)),
            )
        )
        for item in parliament_items
    )
    payload = "\n".join(sorted(records)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_delivery_id(run_id: str, status: str, data_fingerprint: str) -> str:
    return f"{run_id}:{status}:{data_fingerprint[:16]}"
