import json

from scripts.compare_parallel_runs import compare, main


def summary(fingerprint="abc", count=3):
    return {
        "run_id": "uk-news-2026-07-20_2026-08-02",
        "period_start": "2026-07-20",
        "period_end": "2026-08-02",
        "all_news_count": count,
        "filtered_news_count": 2,
        "parliament_count": 1,
        "filtered_parliament_count": 1,
        "data_fingerprint": fingerprint,
    }


def test_compare_requires_counts_and_fingerprint_to_match():
    assert compare(summary(), summary())["logical_match"] is True
    assert compare(summary(), summary(count=4))["logical_match"] is False
    assert compare(summary(), summary(fingerprint="changed"))["logical_match"] is False


def test_compare_catches_source_and_provenance_drift():
    original = summary()
    original.update({
        "status": "complete",
        "delivery_id": "delivery-id",
        "source_health": [{"source": "A", "success": True, "item_count": 2, "candidate_count": 2, "duration_seconds": 1, "endpoints": [{"url": "https://example.com/feed", "status_code": 200}]}],
        "record_provenance": [{"record_type": "news", "source_id": "A", "canonical_url": "https://example.com/a", "source_feed": "feed", "parser_version": "v1", "fetched_at": "first"}],
        "observability": {"source_count": 1, "source_success_rate": 1.0, "zero_item_ratio": 0.0, "source_p95_seconds": 1.0},
    })
    same = json.loads(json.dumps(original))
    same["source_health"][0]["duration_seconds"] = 9
    same["record_provenance"][0]["fetched_at"] = "second"
    same["observability"]["source_p95_seconds"] = 9
    assert compare(original, same)["logical_match"] is True
    same["record_provenance"][0]["canonical_url"] = "https://example.com/b"
    assert compare(original, same)["logical_match"] is False
    same["record_provenance"][0]["canonical_url"] = "https://example.com/a"
    same["source_health"][0]["success"] = False
    assert compare(original, same)["logical_match"] is False


def test_three_consecutive_parallel_runs_gate(tmp_path, monkeypatch):
    python_summary = tmp_path / "python.run.json"
    rust_summary = tmp_path / "rust.run.json"
    history = tmp_path / "parallel-history.json"
    python_summary.write_text(json.dumps(summary()), encoding="utf-8")
    rust_summary.write_text(json.dumps(summary()), encoding="utf-8")
    for expected in (1, 1, 0):
        monkeypatch.setattr(
            "sys.argv",
            [
                "compare",
                "--python-summary",
                str(python_summary),
                "--rust-summary",
                str(rust_summary),
                "--history",
                str(history),
                "--require-consecutive",
                "3",
            ],
        )
        assert main() == expected
    assert len(json.loads(history.read_text(encoding="utf-8"))) == 3
