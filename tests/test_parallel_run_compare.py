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
