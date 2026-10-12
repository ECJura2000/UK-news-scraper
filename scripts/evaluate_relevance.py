from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from UK_news_scraper.profiles import default_profile, profile_hash
from UK_news_scraper.relevance import assess_relevance

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "tests/fixtures/relevance_quality_v1.json"


def evaluate(dataset: dict) -> dict:
    cases = dataset["cases"]
    ids = [case["id"] for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("驗證集不能為空或有重複 ID")
    counts = dict(tp=0, fp=0, tn=0, fn=0)
    results = []
    for case in cases:
        label = case["label"]
        if label not in {"related", "unrelated", "boundary"}:
            raise ValueError(f"未知標記：{label}")
        assessment = assess_relevance(case["title"], case.get("summary", ""))
        if label != "boundary":
            key = (
                ("tp" if assessment.included else "fn")
                if label == "related"
                else ("fp" if assessment.included else "tn")
            )
            counts[key] += 1
        results.append(
            {
                **case,
                "included": assessment.included,
                "score": assessment.score,
                "keywords": assessment.keywords,
                "topics": assessment.topics,
            }
        )
    precision_base = counts["tp"] + counts["fp"]
    recall_base = counts["tp"] + counts["fn"]
    return {
        "dataset_sha256": hashlib.sha256(json.dumps(dataset, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "profile_hash": profile_hash(default_profile()),
        "counts": counts,
        "precision_on_labeled_cases": counts["tp"] / precision_base if precision_base else None,
        "recall_on_labeled_cases": counts["tp"] / recall_base if recall_base else None,
        "boundary_count": sum(case["label"] == "boundary" for case in cases),
        "limitations": dataset.get("limitations", "Not a representative sample."),
        "provenance": dataset.get("provenance", ""),
        "results": results,
    }


def compare(current: dict, baseline: dict) -> dict:
    if current["dataset_sha256"] != baseline.get("dataset_sha256"):
        raise ValueError("驗證集不同，不能比較")
    prior = {case["id"]: case["included"] for case in baseline["results"]}
    if set(prior) != {case["id"] for case in current["results"]}:
        raise ValueError("基準案例不完整")
    changes = [case for case in current["results"] if case["included"] != prior[case["id"]]]
    regressions = [
        case
        for case in changes
        if (case["label"] == "related" and not case["included"]) or (case["label"] == "unrelated" and case["included"])
    ]
    return {"changes": changes, "regressions": regressions}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate fixed labels; boundary cases remain review-only.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.dataset.read_text(encoding="utf-8")))
    if args.baseline:
        result["comparison"] = compare(result, json.loads(args.baseline.read_text(encoding="utf-8")))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "results"}, ensure_ascii=False, indent=2))
    return int(bool(result.get("comparison", {}).get("regressions")))


if __name__ == "__main__":
    raise SystemExit(main())
