from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile


COUNT_FIELDS = (
    "all_news_count",
    "filtered_news_count",
    "parliament_count",
    "filtered_parliament_count",
)


def compare(python_summary: dict, rust_summary: dict) -> dict:
    fields = {
        field: {
            "python": python_summary.get(field),
            "rust": rust_summary.get(field),
            "match": python_summary.get(field) == rust_summary.get(field),
        }
        for field in COUNT_FIELDS
    }
    fields["data_fingerprint"] = {
        "python": python_summary.get("data_fingerprint"),
        "rust": rust_summary.get("data_fingerprint"),
        "match": python_summary.get("data_fingerprint")
        == rust_summary.get("data_fingerprint"),
    }
    return {
        "compared_at": datetime.now(timezone.utc).isoformat(),
        "period_start": python_summary.get("period_start"),
        "period_end": python_summary.get("period_end"),
        "python_run_id": python_summary.get("run_id"),
        "rust_run_id": rust_summary.get("run_id"),
        "fields": fields,
        "logical_match": all(value["match"] for value in fields.values()),
        "explanation": "",
    }


def atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record Python/Rust weekly logical-output compatibility."
    )
    parser.add_argument("--python-summary", type=Path, required=True)
    parser.add_argument("--rust-summary", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--explanation", default="")
    parser.add_argument("--require-consecutive", type=int, default=0)
    args = parser.parse_args()
    python_summary = json.loads(args.python_summary.read_text(encoding="utf-8"))
    rust_summary = json.loads(args.rust_summary.read_text(encoding="utf-8"))
    if (
        python_summary.get("period_start") != rust_summary.get("period_start")
        or python_summary.get("period_end") != rust_summary.get("period_end")
    ):
        parser.error("summaries cover different periods")
    record = compare(python_summary, rust_summary)
    record["explanation"] = args.explanation
    history = []
    if args.history.exists():
        history = json.loads(args.history.read_text(encoding="utf-8"))
    history.append(record)
    atomic_write(args.history, history)
    consecutive = 0
    for item in reversed(history):
        if item.get("logical_match"):
            consecutive += 1
        else:
            break
    print(json.dumps({"record": record, "consecutive_matches": consecutive}, ensure_ascii=False))
    if args.require_consecutive and consecutive < args.require_consecutive:
        return 1
    return 0 if record["logical_match"] or bool(args.explanation.strip()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
