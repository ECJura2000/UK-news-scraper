from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path


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
