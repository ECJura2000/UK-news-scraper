from copy import deepcopy

import pytest

from scripts.performance_baseline import record, report


def entry(number=1):
    summary = dict(
        all_news_count=2,
        filtered_news_count=1,
        parliament_count=0,
        filtered_parliament_count=0,
        run_id="test",
        delivery_id="delivery",
        status="complete",
        data_fingerprint="fingerprint",
        output_file="test.xlsx",
        generated_at=f"2026-10-11T00:0{number}:00Z",
        period_start="2026-10-01",
        period_end="2026-10-07",
        profile_hash="profile",
        selected_sources=["ICO"],
        source_health=[dict(source="ICO", success=True, item_count=2)],
        performance=dict(
            schema_version=1,
            runtime="python",
            runtime_version="2.3.6",
            workers=8,
            run_kind="full",
            total_endpoint="before_summary_serialization",
            total_wall_seconds=number * 10,
            stages={"json_write_seconds": None},
        ),
    )
    return record(summary, revision="commit", machine="test-machine", cache_state="cold", cache_key="empty")


def test_three_distinct_runs_required_and_missing_stages_stay_unknown():
    results = report([entry(1), entry(2), entry(3), entry(3)])["groups"]
    assert len(results) == 1
    assert results[0]["sample_count"] == 3
    assert results[0]["baseline_ready"]
    assert results[0]["wall_seconds"] == dict(median=20, p95=30, min=10, max=30)
    assert results[0]["stages"]["json_write_seconds"] is None
    assert not report([entry()])["groups"][0]["baseline_ready"]


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("context", "machine", "different"),
        ("context", "cache_key", "changed"),
        ("context", "revision", "changed"),
        ("summary", "data_fingerprint", "changed"),
        ("summary", "profile_hash", "changed"),
        ("summary", "status", "degraded"),
        ("performance", "run_kind", "retry"),
        ("performance", "runtime", "rust"),
        ("performance", "translation_cache_hits", 2),
    ],
)
def test_different_conditions_never_share_a_baseline(section, key, value):
    other = entry(2)
    target = other["summary"]["performance"] if section == "performance" else other[section]
    target[key] = value
    assert len(report([entry(1), other])["groups"]) == 2


def test_unmeasured_or_invalid_baselines_are_rejected():
    for value in (0, -1, float("nan"), float("inf"), True, None):
        invalid = entry()
        invalid["summary"]["performance"]["total_wall_seconds"] = value
        with pytest.raises(ValueError):
            report([invalid])
    invalid = deepcopy(entry())
    del invalid["summary"]["profile_hash"]
    with pytest.raises(ValueError, match="profile_hash"):
        report([invalid])


def test_conflicting_metadata_for_the_same_execution_is_rejected():
    other = entry()
    other["context"]["machine"] = "different"
    with pytest.raises(ValueError, match="互相衝突"):
        report([entry(), other])
