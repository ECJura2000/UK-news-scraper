from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

from .models import NewsItem, ParliamentBriefing, SourceHealth


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
    records = [
        f"news|{item.agency}|{item.date_text}|{item.title}|{item.link}"
        for item in news_items
    ]
    records.extend(
        f"parliament|{item.publisher}|{item.date_text}|{item.identifier}|{item.title}|{item.webpage_url}"
        for item in parliament_items
    )
    payload = "\n".join(sorted(records)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_delivery_id(run_id: str, status: str, data_fingerprint: str) -> str:
    return f"{run_id}:{status}:{data_fingerprint[:16]}"
