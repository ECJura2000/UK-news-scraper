from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import median

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from UK_news_scraper.run_summary import validate_run_summary_payload


def record(summary: dict, *, revision: str, machine: str, cache_state: str, cache_key: str) -> dict:
    validate_run_summary_payload(summary)
    performance = summary.get("performance", {})
    duration = performance.get("total_wall_seconds")
    if (
        performance.get("schema_version") != 1
        or not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("摘要沒有有效的實測效能，舊摘要不能當作零秒基準")
    if any(not value.strip() for value in (revision, machine, cache_key)) or cache_state not in {"cold", "warm"}:
        raise ValueError("必須明確記錄當次版本、機器與翻譯快取條件")
    for key in ("period_start", "period_end", "profile_hash", "selected_sources", "source_health"):
        if not summary.get(key):
            raise ValueError(f"摘要缺少比較條件：{key}")
    for key in ("runtime", "runtime_version", "workers", "run_kind", "total_endpoint"):
        if not performance.get(key):
            raise ValueError(f"摘要缺少效能條件：{key}")
    for key in ("all_news_count", "filtered_news_count", "parliament_count", "filtered_parliament_count"):
        if type(summary.get(key)) is not int or summary[key] < 0:
            raise ValueError(f"摘要缺少有效邏輯筆數：{key}")
    if performance["run_kind"] not in {"full", "retry"}:
        raise ValueError("未知執行類型")
    return {
        "schema_version": 1,
        "context": {"revision": revision, "machine": machine, "cache_state": cache_state, "cache_key": cache_key},
        "summary": summary,
    }


def group_key(entry: dict) -> str:
    summary = entry["summary"]
    p = summary["performance"]
    # Different data, source health, cache conditions or revisions never share a baseline.
    contract = {
        "context": entry["context"],
        "summary": {
            key: summary[key] for key in ("period_start", "period_end", "profile_hash", "status", "data_fingerprint")
        },
        "sources": sorted(summary["selected_sources"]),
        "health": sorted(
            (s["source"], s["success"], s.get("item_count", 0), s.get("warning", "")) for s in summary["source_health"]
        ),
        "performance": {
            key: p.get(key)
            for key in (
                "schema_version",
                "runtime",
                "runtime_version",
                "workers",
                "run_kind",
                "total_endpoint",
                "translation_cache_hits",
                "translation_cache_misses",
            )
        },
        "counts": {
            key: summary.get(key)
            for key in ("all_news_count", "filtered_news_count", "parliament_count", "filtered_parliament_count")
        },
    }
    return json.dumps(contract, ensure_ascii=False, sort_keys=True)


def distribution(values: list[float]) -> dict:
    values = sorted(values)
    return {
        "median": median(values),
        "p95": values[math.ceil(len(values) * 0.95) - 1],
        "min": values[0],
        "max": values[-1],
    }


def report(entries: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    seen = {}
    for entry in entries:
        record(entry["summary"], **entry["context"])
        # Reading the same measured execution twice must not create two samples.
        identity = (entry["summary"].get("generated_at"), entry["summary"]["run_id"], entry["summary"]["output_file"])
        if not identity[0]:
            raise ValueError("摘要缺少 generated_at，無法排除重複執行紀錄")
        signature = json.dumps(entry, sort_keys=True)
        if identity in seen:
            if seen[identity] != signature:
                raise ValueError("同一次執行出現互相衝突的摘要或條件")
            continue
        seen[identity] = signature
        groups.setdefault(group_key(entry), []).append(entry)
    result = []
    for key, group in groups.items():
        durations = [entry["summary"]["performance"]["total_wall_seconds"] for entry in group]
        stages = {}
        names = set().union(*(entry["summary"]["performance"].get("stages", {}) for entry in group))
        for name in sorted(names):
            values = [entry["summary"]["performance"].get("stages", {}).get(name) for entry in group]
            stages[name] = (
                distribution(values)
                if all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values)
                else None
            )
        result.append(
            {
                "group_id": hashlib.sha256(key.encode()).hexdigest()[:12],
                "conditions": json.loads(key),
                "sample_count": len(group),
                "baseline_ready": len(group) >= 3
                and group[0]["summary"]["performance"]["run_kind"] == "full"
                and group[0]["summary"]["status"] == "complete",
                "wall_seconds": distribution(durations),
                "stages": stages,
            }
        )
    return {
        "groups": result,
        "note": (
            "各組獨立；完整執行至少三次才可建立基準。重試、降級與不同條件分組；"
            "各階段可重疊，不能加總。此工具不宣稱加速幅度。"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record explicit run conditions and summarize comparable measurements."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("record")
    capture.add_argument("--summary", required=True, type=Path)
    for field in ("revision", "machine", "cache-key"):
        capture.add_argument(f"--{field}", required=True)
    capture.add_argument("--cache-state", choices=("cold", "warm"), required=True)
    capture.add_argument("--output", required=True, type=Path)
    analyze = commands.add_parser("report")
    analyze.add_argument("inputs", nargs="+", type=Path)
    analyze.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "record":
        result = record(
            json.loads(args.summary.read_text(encoding="utf-8")),
            revision=args.revision,
            machine=args.machine,
            cache_state=args.cache_state,
            cache_key=args.cache_key,
        )
    else:
        result = report([json.loads(path.read_text(encoding="utf-8")) for path in args.inputs])
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    if args.command == "report":
        print(encoded)


if __name__ == "__main__":
    main()
