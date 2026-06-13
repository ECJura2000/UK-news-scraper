import json
import sys


payload = json.load(open(sys.argv[1], encoding="utf-8"))
baseline = json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else None
budgets = {"1000": 10.0, "10000": 30.0}
for size, limit in budgets.items():
    if size not in payload["dedupe"]:
        continue
    actual = float(payload["dedupe"][size]["p95_ms"])
    if actual > limit:
        print(f"::warning::UK dedupe P95 {size} rows is {actual:.3f} ms, budget {limit:.3f} ms")
    if baseline and size in baseline.get("dedupe", {}):
        previous = float(baseline["dedupe"][size]["p95_ms"])
        if previous and actual > previous * 1.30:
            print(f"::warning::UK dedupe P95 {size} rows regressed more than 30%")
