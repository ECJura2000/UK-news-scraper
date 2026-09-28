"""Exercise the desktop contract with real widgets and offline run results."""

import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from UK_news_scraper.app_service import ProgressEvent, RunRequest, RunResult
from UK_news_scraper.models import NewsItem, RunStatus, SourceHealth
from UK_news_scraper.profiles import ProfileLoadReport, default_profile, profile_to_dict
from UK_news_scraper.run_summary import RunSummary
from UK_news_scraper.ui_state import RunHistoryEntry


def _tk_available() -> bool:
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return False
    probe = subprocess.run(
        [sys.executable, "-c", "import tkinter as tk; root = tk.Tk(); root.destroy()"],
        capture_output=True,
        check=False,
        timeout=5,
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _tk_available(), reason="Tk requires an available graphical session")


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    from UK_news_scraper import ui

    profile = default_profile()
    monkeypatch.setattr(ui, "load_profiles_with_recovery", lambda: ProfileLoadReport({profile.profile_id: profile}))
    monkeypatch.setattr(ui, "load_run_history", lambda _path: [])
    monkeypatch.setattr(ui, "save_profiles", lambda _profiles: None)
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui.messagebox, "showwarning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *_args, **_kwargs: None)
    app = ui.UKNewsApp()
    app.output_dir_var.set(str(tmp_path))
    yield app, ui
    if app.winfo_exists():
        app.destroy()


def _result(tmp_path: Path) -> RunResult:
    item = NewsItem(
        agency="Ofcom",
        agency_en="Ofcom",
        unit_category="Ofcom",
        title="Digital platforms and online safety guidance",
        link="https://example.org/news",
        published_at=datetime(2026, 9, 20, tzinfo=UTC),
        summary="Online safety guidance",
        matched_topics=["數位平台"],
        matched_keywords=["online safety"],
        title_matched_keywords=["online safety"],
        title_keyword_strengths={"online safety": "core"},
        relevance_score=8,
        relevance_level="高",
    )
    output = tmp_path / "report.xlsx"
    output.write_bytes(b"workbook fixture")
    summary = RunSummary(
        run_id="uk-news-2026-09-14_2026-09-28",
        generated_at="2026-09-28T00:00:00+00:00",
        period_start="2026-09-14",
        period_end="2026-09-28",
        output_file=str(output),
        all_news_count=1,
        filtered_news_count=1,
        parliament_count=0,
        filtered_parliament_count=0,
        status=RunStatus.DEGRADED,
        warnings=("Ofcom source warning",),
        data_fingerprint="v3:test",
        delivery_id="uk-news-test",
        source_health=(SourceHealth("Ofcom", True, False, 0, 0.1, warning="source warning"),),
    )
    return RunResult(output, output.with_suffix(".run.json"), summary, (item,), (item,), (), ())


def test_profile_editing_and_date_controls(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    answers = iter(["Custom profile", "Copy profile", "New topic", "New phrase", "核心", "Edited phrase", "核心"])
    monkeypatch.setattr(ui.simpledialog, "askstring", lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **_kwargs: str(tmp_path))

    app._new_profile()
    assert app._profile_from_form().name == "Custom profile"
    app._duplicate_profile()
    assert len(app._profiles) == 3
    app._save_profile()
    app._add_topic()
    app.topic_tree.selection_set(str(len(app._edit_topics) - 1))
    app._refresh_keywords(len(app._edit_topics) - 1)
    app._add_keyword()
    assert app._edit_topics[-1]["keywords"]
    app.keyword_tree.selection_set("0")
    app._edit_keyword()
    app._delete_keyword()
    app._delete_topic()
    app.ui_calendar_var.set("民國")
    app._calendar_changed()
    app._choose_output_dir()
    assert app.start_selector.get() <= app.end_selector.get()
    app._delete_profile()
    app._restore_profiles()
    assert app._profiles


def test_run_result_retry_filters_and_history(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    result = _result(tmp_path)
    launched = []
    monkeypatch.setattr(app, "_launch_run", launched.append)
    app._start_run()
    assert isinstance(launched[-1], RunRequest)
    app._last_request = launched[-1]
    app._handle_progress(ProgressEvent("fetch_news", "Fetching", 1, 5))
    app._handle_result(result)
    assert app.result_tree.get_children()
    assert str(app.retry_button["state"]) == "normal"
    app._retry_failed_sources()
    assert launched[-1].retry_source_ids == ("Ofcom",)

    app.search_var.set("online safety")
    app._refresh_results()
    assert len(app.result_tree.get_children()) == 1
    app.result_tree.selection_set("0")
    app._result_selected()
    assert "Digital platforms" in app.detail_title_var.get()
    app._sort_results("date")
    app._clear_result_filters()
    app.result_min_score_var.set("invalid")
    app._refresh_results()
    assert "格式無效" in app.result_count_var.get()
    app.result_min_score_var.set("10")
    app.result_max_score_var.set("1")
    app._refresh_results()
    assert "最低分" in app.result_count_var.get()

    opened = []
    monkeypatch.setattr(ui.webbrowser, "open", opened.append)
    app._open_source()
    assert opened == ["https://example.org/news"]
    monkeypatch.setattr(app, "_open_path", opened.append)
    app._open_workbook()
    assert opened[-1] == result.workbook_path

    entry = RunHistoryEntry(
        result.summary_path,
        result.workbook_path,
        datetime(2026, 9, 28, tzinfo=UTC),
        date(2026, 9, 14),
        date(2026, 9, 28),
        "degraded",
        "UK 科技法制",
        1,
        1,
        0,
    )
    monkeypatch.setattr(ui, "load_run_history", lambda _path: [entry])
    app._refresh_history()
    app.history_tree.selection_set("0")
    app._open_history_workbook()
    app._open_history_summary()
    assert opened[-2:] == [result.workbook_path, result.summary_path]


def test_worker_queue_and_cancel_paths(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    result = _result(tmp_path)
    request = RunRequest(date(2026, 9, 14), date(2026, 9, 28))
    monkeypatch.setattr(ui, "execute_run", lambda _request, **_kwargs: result)
    app._run_worker(request)
    app._poll_queue()
    assert app._result == result

    class PendingThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(ui.threading, "Thread", PendingThread)
    app._launch_run(request)
    app._cancel_run()
    assert app._cancel_event.is_set()
    app._queue.put(("cancelled", RuntimeError("cancelled")))
    app._poll_queue()
    assert app.run_status_var.get() == "執行已取消"
    app._queue.put(("error", RuntimeError("offline failure")))
    app._poll_queue()
    assert app.run_status_var.get() == "執行失敗"


def test_profile_import_export_and_invalid_run_guard(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    imported = tmp_path / "import.json"
    imported.write_text(json.dumps(profile_to_dict(default_profile())), encoding="utf-8")
    exported = tmp_path / "export.json"
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **_kwargs: str(imported))
    monkeypatch.setattr(ui.filedialog, "asksaveasfilename", lambda **_kwargs: str(exported))
    monkeypatch.setattr(ui.simpledialog, "askstring", lambda *_args, **_kwargs: "Renamed topic")
    app._import_profile()
    assert "uk-tech-law-imported" in app._profiles
    app._export_profile()
    assert json.loads(exported.read_text(encoding="utf-8"))["profile_id"] == "uk-tech-law-imported"

    app.topic_tree.selection_set("0")
    app._rename_topic()
    assert app._edit_topics[0]["name"] == "Renamed topic"

    launched = []
    monkeypatch.setattr(app, "_launch_run", launched.append)
    app.start_selector.set(date(2026, 9, 28))
    app.end_selector.set(date(2026, 9, 14))
    app._start_run()
    assert not launched


def test_missing_files_and_worker_failures_stay_in_the_ui(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    opened = []
    monkeypatch.setattr(ui.subprocess, "Popen", lambda args: opened.append(args))
    app._open_path(tmp_path / "missing.xlsx")
    assert not opened
    existing = tmp_path / "report.xlsx"
    existing.write_bytes(b"fixture")
    app._open_path(existing)
    assert opened and str(existing) in opened[0]

    def fail(_request, **_kwargs):
        raise RuntimeError("offline failure")

    monkeypatch.setattr(ui, "execute_run", fail)
    app._run_worker(RunRequest(date(2026, 9, 14), date(2026, 9, 28)))
    app._poll_queue()
    assert app.run_status_var.get() == "執行失敗"

    from UK_news_scraper.app_service import RunCancelled

    def cancel(_request, **_kwargs):
        raise RunCancelled("cancelled")

    monkeypatch.setattr(ui, "execute_run", cancel)
    app._run_worker(RunRequest(date(2026, 9, 14), date(2026, 9, 28)))
    app._poll_queue()
    assert app.run_status_var.get() == "執行已取消"


def test_ui_profile_guard_and_dialog_cancellation(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    messages = []
    monkeypatch.setattr(ui.messagebox, "showwarning", lambda *args: messages.append(args))
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *args: messages.append(args))
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *args: False)
    monkeypatch.setattr(ui.simpledialog, "askstring", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **kwargs: "")
    monkeypatch.setattr(ui.filedialog, "asksaveasfilename", lambda **kwargs: "")
    app._save_profile()
    app._restore_profiles()
    app._new_profile()
    app._duplicate_profile()
    app._delete_profile()
    app._import_profile()
    app._export_profile()
    app._add_topic()
    app.topic_tree.selection_remove(*app.topic_tree.selection())
    app._rename_topic()
    app._add_keyword()
    app._delete_topic()
    app._edit_keyword()
    app._delete_keyword()
    app._ask_strength()
    app._retry_failed_sources()
    app._open_workbook()
    app._open_source()
    app._open_history_workbook()
    app._open_history_summary()
    assert messages


def test_ui_profile_import_and_strength_errors(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    errors = []
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *args: errors.append(args))
    monkeypatch.setattr(ui.simpledialog, "askstring", lambda *args, **kwargs: "invalid")
    assert app._ask_strength() is None
    imported = tmp_path / "bad.json"
    imported.write_text("{", encoding="utf-8")
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **kwargs: str(imported))
    app._import_profile()
    assert len(errors) == 2
    app.profile_name_var.set("")
    app._save_profile()
    app._export_profile()
    assert len(errors) == 4


def test_ui_run_controls_reject_concurrent_work_and_no_failed_sources(desktop, monkeypatch, tmp_path):
    app, ui = desktop
    messages = []
    monkeypatch.setattr(ui.messagebox, "showwarning", lambda *args: messages.append(args))
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *args: messages.append(args))
    result = _result(tmp_path)
    app._result = result
    app._last_request = RunRequest(date(2026, 9, 14), date(2026, 9, 28))
    monkeypatch.setattr(ui, "failed_source_ids", lambda _health: ())
    app._retry_failed_sources()

    class LiveThread:
        def is_alive(self):
            return True

    app._run_thread = LiveThread()
    app._launch_run(app._last_request)
    assert len(messages) == 2
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *args: False)
    app._on_close()
    assert app.winfo_exists()
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *args: True)
    app._on_close()
    assert app._closing


def test_date_selector_handles_roc_leap_day_and_invalid_entries(desktop):
    app, _ui = desktop
    from UK_news_scraper.calendar_utils import CalendarMode
    from UK_news_scraper.ui_components import DateSelector

    changed = []
    selector = DateSelector(app, date(2024, 2, 29), command=lambda: changed.append(True))
    selector.set_mode(CalendarMode.ROC)
    assert selector.get() == date(2024, 2, 29)
    selector.month_var.set("02月")
    selector.year_var.set("民國114年")
    selector._selection_changed()
    assert selector.get() == date(2025, 2, 28)
    assert changed
    selector.year_var.set("invalid")
    assert selector.get() == date(2025, 2, 28)
    selector._refresh_days(31)
    selector.set_mode(CalendarMode.GREGORIAN)
    selector.set(date(2026, 3, 31))
    assert selector.get() == date(2026, 3, 31)
    selector.destroy()


def test_ui_navigation_and_profile_selection(desktop):
    app, _ui = desktop
    app._show_page("profiles")
    app._show_page("run")
    app._profile_selected()
    app._run_profile_selected()
    app.scale_var.set("125%")
    app._change_scale()
    app._sort_results("score")
    app._clear_result_filters()
    assert app.profile_id_var.get() == "uk-tech-law"
