from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Append one verified result to a JSONL history.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=Path("reports/long-term-runs.jsonl"), type=Path)
    parser.add_argument("--kind", default="run-summary")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "kind": args.kind, "payload": payload}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
