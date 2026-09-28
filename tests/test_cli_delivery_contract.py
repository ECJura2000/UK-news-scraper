"""The CLI and delivery registry keep their offline output and idempotency contracts."""

import json
import sys
from datetime import UTC, date, datetime

from UK_news_scraper import delivery_registry, main
from UK_news_scraper.app_service import RunResult
from UK_news_scraper.models import NewsItem, RunStatus
from UK_news_scraper.run_summary import RunSummary


def _run_result(tmp_path):
    workbook = tmp_path / "report.xlsx"
    workbook.write_bytes(b"offline workbook")
    summary = RunSummary(
        run_id="uk-news-2026-09-14_2026-09-28",
        generated_at="2026-09-28T00:00:00+00:00",
        period_start="2026-09-14",
        period_end="2026-09-28",
        output_file=str(workbook),
        all_news_count=1,
        filtered_news_count=0,
        parliament_count=0,
        filtered_parliament_count=0,
        status=RunStatus.DEGRADED,
        warnings=("offline source warning",),
        data_fingerprint="v3:fixture",
        delivery_id="uk-news-fixture",
        source_health=(),
    )
    item = NewsItem("Agency", "Agency", "A", "Title", "https://example.org", datetime(2026, 9, 20, tzinfo=UTC))
    return RunResult(workbook, workbook.with_suffix(".run.json"), summary, (item,), (), (), ())


def test_default_cli_uses_app_service_summary_without_transport(monkeypatch, tmp_path, capsys):
    result = _run_result(tmp_path)
    requests = []
    monkeypatch.setattr(main, "execute_run", lambda request: requests.append(request) or result)
    monkeypatch.setattr(sys, "argv", ["uk", "20260914～20260928", "--output", str(result.workbook_path)])

    main.main()

    assert requests[0].period_start == date(2026, 9, 14)
    assert requests[0].period_end == date(2026, 9, 28)
    assert requests[0].output_path == result.workbook_path
    output = capsys.readouterr().out
    assert "全部新聞：1 筆" in output
    assert "抓取狀態：部分來源抓取失敗" in output
    assert "uk-news-2026-09-14_2026-09-28" in output


def test_cli_runtime_and_ui_modes_do_not_collect(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["uk", "--check-runtime"])
    main.main()
    assert "封裝執行環境檢查通過" in capsys.readouterr().out

    launched = []
    from UK_news_scraper import ui

    monkeypatch.setattr(ui, "launch", lambda: launched.append(True))
    monkeypatch.setattr(sys, "argv", ["uk", "--ui"])
    main.main()
    assert launched == [True]


def test_registry_cli_claim_complete_and_recovery_are_idempotent(monkeypatch, tmp_path, capsys):
    summary = tmp_path / "report.run.json"
    summary.write_text(
        json.dumps(
            {
                "delivery_id": "delivery-fixture",
                "run_id": "run-fixture",
                "status": "degraded",
                "data_fingerprint": "v3:fixture",
                "output_file": str(tmp_path / "report.xlsx"),
            }
        ),
        encoding="utf-8",
    )
    registry = tmp_path / "registry.json"
    monkeypatch.setenv("UK_NEWS_DISABLE_NATIVE_REGISTRY_SHIM", "1")

    def invoke(*args):
        monkeypatch.setattr(sys, "argv", ["delivery", "--registry", str(registry), *args])
        delivery_registry.main()
        return json.loads(capsys.readouterr().out)

    assert invoke("claim", "--summary", str(summary))["claimed"] is True
    assert invoke("claim", "--summary", str(summary))["claimed"] is False
    assert invoke("status", "--state", "claimed")["count"] == 1
    completed = invoke("complete", "--delivery-id", "delivery-fixture", "--message-id", "gmail-fixture")
    assert completed["state"] == "sent"
    assert completed["message_id"] == "gmail-fixture"
    assert invoke("status", "--delivery-id", "delivery-fixture")["record"]["state"] == "sent"
    assert invoke("claim", "--summary", str(summary))["claimed"] is False
    assert invoke("release", "--delivery-id", "delivery-fixture")["released"] is False

    second = json.loads(summary.read_text(encoding="utf-8"))
    second["delivery_id"] = "second-fixture"
    summary.write_text(json.dumps(second), encoding="utf-8")
    assert invoke("claim", "--summary", str(summary))["claimed"] is True
    assert invoke("recover", "--delivery-id", "second-fixture", "--confirm-release")["released"] is True
    assert invoke("status", "--state", "claimed")["count"] == 0
