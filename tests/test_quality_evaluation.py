import copy
import json

import pytest

from scripts.evaluate_relevance import DEFAULT_DATASET, compare, evaluate


def test_historical_corpus_quality_budget_and_boundary_separation():
    dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    result = evaluate(dataset)
    for case in result["results"]:
        if case["label"] == "related" and case["baseline_included"]:
            assert case["included"], f"新增漏選：{case['title']}"
        if case["label"] == "unrelated" and not case["baseline_included"]:
            assert not case["included"], f"新增誤選：{case['title']}"
    assert result["boundary_count"] == 10
    assert result["counts"]["fp"] <= 1, [r for r in result["results"] if r["included"] and r["label"] == "unrelated"]
    assert result["counts"]["fn"] <= 3, [r for r in result["results"] if not r["included"] and r["label"] == "related"]
    assert sum(result["counts"].values()) + result["boundary_count"] == len(dataset["cases"])
    assert "not newly reviewed" in result["provenance"]


def test_quality_comparison_flags_new_misses_and_ignores_boundary_changes():
    baseline = evaluate(
        {
            "cases": [
                {"id": "a", "title": "Artificial intelligence policy", "label": "related"},
                {"id": "b", "title": "Technology awards", "label": "boundary"},
            ]
        }
    )
    current = copy.deepcopy(baseline)
    current["results"][0]["included"] = False
    current["results"][1]["included"] = True
    assert len(compare(current, baseline)["changes"]) == 2
    assert [r["id"] for r in compare(current, baseline)["regressions"]] == ["a"]
    baseline["dataset_sha256"] = "different"
    with pytest.raises(ValueError, match="驗證集不同"):
        compare(current, baseline)


@pytest.mark.parametrize(
    "cases", [[], [dict(id="a", title="x", label="related")] * 2, [dict(id="a", title="x", label="unknown")]]
)
def test_quality_rejects_invalid_labels(cases):
    with pytest.raises(ValueError):
        evaluate({"cases": cases})


def test_empty_binary_denominators_are_unknown_not_zero():
    result = evaluate({"cases": [{"id": "b", "title": "x", "label": "boundary"}]})
    assert result["precision_on_labeled_cases"] is None
    assert result["recall_on_labeled_cases"] is None
