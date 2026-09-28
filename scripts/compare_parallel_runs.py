from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

COUNT_FIELDS = (
    "all_news_count",
    "filtered_news_count",
    "parliament_count",
    "filtered_parliament_count",
)


def _source_contract(summary: dict) -> list[dict]:
    return sorted(
        (
            {
                "source": source.get("source"),
                "success": source.get("success"),
            }
            for source in summary.get("source_health", ())
        ),
        key=lambda source: source["source"] or "",
    )


def _record_contract(summary: dict) -> list[dict]:
    return sorted(
        (
            {
                key: record.get(key) or ""
                for key in ("record_type", "source_id", "canonical_url", "source_feed", "parser_version")
            }
            for record in summary.get("record_provenance", ())
        ),
        key=lambda record: tuple(record.values()),
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
        "match": python_summary.get("data_fingerprint") == rust_summary.get("data_fingerprint"),
    }
    fields["status"] = {
        "python": python_summary.get("status"),
        "rust": rust_summary.get("status"),
        "match": python_summary.get("status") == rust_summary.get("status"),
    }
    for field in ("status", "delivery_id", "profile_hash"):
        if field in python_summary or field in rust_summary:
            fields[field] = {
                "python": python_summary.get(field),
                "rust": rust_summary.get(field),
                "match": python_summary.get(field) == rust_summary.get(field),
            }
    for field, normalize in (("source_health", _source_contract), ("record_provenance", _record_contract)):
        if field in python_summary or field in rust_summary:
            python_value = normalize(python_summary)
            rust_value = normalize(rust_summary)
            fields[field] = {
                "python": python_value,
                "rust": rust_value,
                "match": python_value == rust_value and field in python_summary and field in rust_summary,
            }
    if "observability" in python_summary or "observability" in rust_summary:
        keys = ("source_count", "source_success_rate")
        python_value = {key: python_summary.get("observability", {}).get(key) for key in keys}
        rust_value = {key: rust_summary.get("observability", {}).get(key) for key in keys}
        fields["observability"] = {
            "python": python_value,
            "rust": rust_value,
            "match": python_value == rust_value
            and "observability" in python_summary
            and "observability" in rust_summary,
        }
    return {
        "compared_at": datetime.now(UTC).isoformat(),
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
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Python/Rust weekly logical-output compatibility.")
    parser.add_argument("--python-summary", type=Path, required=True)
    parser.add_argument("--rust-summary", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--explanation", default="")
    parser.add_argument("--require-consecutive", type=int, default=0)
    args = parser.parse_args()
    python_summary = json.loads(args.python_summary.read_text(encoding="utf-8"))
    rust_summary = json.loads(args.rust_summary.read_text(encoding="utf-8"))
    if python_summary.get("period_start") != rust_summary.get("period_start") or python_summary.get(
        "period_end"
    ) != rust_summary.get("period_end"):
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
