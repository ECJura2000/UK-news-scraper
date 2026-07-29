from __future__ import annotations

import argparse
import hmac
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .app_service import (
    ExportOptionsRequest,
    RunRequest,
    evaluate_run_status,
    execute_run,
)
from .calendar_utils import CalendarMode
from .config import (
    DEFAULT_DAYS_BACK,
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TIMEZONE,
)
from .logging_utils import log_event
from .profiles import load_profile
from .runtime_lock import LockUnavailable


PASSWORD_REQUIRED_AFTER_DAYS = 30
FIRST_RUN_FILENAME = ".uknews_first_run"
LOCAL_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取英國相關機關新聞稿，優先使用 RSS/Atom，並依觀測領域初步篩選。"
    )
    parser.add_argument(
        "period",
        nargs="*",
        help="可輸入天數、起始日期或日期區間，例如：30、20160501、20160501～20160515。",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"回推天數；若未提供日期參數，預設 {DEFAULT_DAYS_BACK} 天。",
    )
    parser.add_argument(
        "--since",
        help="指定起始日期 YYYY-MM-DD；若有提供會覆蓋 --days。",
    )
    parser.add_argument(
        "--until",
        help="指定結束日期 YYYY-MM-DD 或 YYYYMMDD，會包含該日期當天。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=f"輸出 xlsx 路徑；預設輸出到 {DEFAULT_OUTPUT_DIR}/起始日-結束日_UK新聞查詢.xlsx。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"併發抓取 worker 數，預設 {DEFAULT_MAX_WORKERS}。",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="設定檔 ID 或 JSON 路徑；預設使用 UK 科技法制。",
    )
    parser.add_argument(
        "--excel-calendar",
        choices=tuple(mode.value for mode in CalendarMode),
        default=CalendarMode.GREGORIAN.value,
        help="Excel 日期紀年：gregorian（西元）或 roc（民國）。",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="啟動高 DPI 桌面介面。",
    )
    parser.add_argument(
        "--check-runtime",
        action="store_true",
        help="驗證封裝所需模組與 scraper registry，不執行網路抓取。",
    )
    return parser.parse_args()


def main(require_trial_password: bool = False) -> None:
    args = parse_args()
    if args.ui:
        from .ui import launch

        launch()
        return
    if args.check_runtime:
        _check_runtime()
        return
    now = datetime.now(timezone.utc)
    if require_trial_password:
        _require_password_after_trial(now)
    since, until = _resolve_date_range(args, now)
    period_start = _local_date(since)
    period_end = _local_date(until - timedelta(microseconds=1))
    try:
        profile = load_profile(args.profile)
        _execute_run(
            args,
            period_start,
            period_end,
            profile,
            CalendarMode(args.excel_calendar),
        )
    except (LockUnavailable, ValueError) as exc:
        raise SystemExit(f"[error] {exc}") from exc


def _check_runtime() -> None:
    import bs4
    import feedparser
    import openpyxl
    import requests
    import tkinter

    from .scrapers.ministry.registry import build_scrapers

    scrapers = build_scrapers()
    if not scrapers:
        raise RuntimeError("scraper registry is empty")
    dependency_names = (
        bs4.__name__,
        feedparser.__name__,
        openpyxl.__name__,
        requests.__name__,
        tkinter.__name__,
    )
    print(
        "封裝執行環境檢查通過；"
        f"scrapers={len(scrapers)} dependencies={','.join(dependency_names)}"
    )


def _execute_run(args, period_start, period_end, profile, calendar_mode) -> None:
    result = execute_run(
        RunRequest(
            period_start=period_start,
            period_end=period_end,
            output_path=Path(args.output) if args.output else None,
            workers=args.workers,
            profile=profile,
            export_options=ExportOptionsRequest(calendar_mode=calendar_mode),
        )
    )
    summary = result.summary
    log_event(
        "done",
        "run_id",
        f"Run ID：{summary.run_id}",
        run_id=summary.run_id,
        delivery_id=summary.delivery_id,
    )
    log_event("done", "all_news_count", f"全部新聞：{summary.all_news_count} 筆", count=summary.all_news_count)
    log_event(
        "done",
        "filtered_news_count",
        f"初步篩選：{summary.filtered_news_count} 筆",
        count=summary.filtered_news_count,
    )
    log_event(
        "done",
        "parliament_count",
        f"國會研究資料：{summary.parliament_count} 筆",
        count=summary.parliament_count,
    )
    log_event(
        "done",
        "filtered_parliament_count",
        f"初步篩選研究資料：{summary.filtered_parliament_count} 筆",
        count=summary.filtered_parliament_count,
    )
    log_event("done", "output_file", f"輸出檔案：{result.workbook_path}", path=str(result.workbook_path))
    log_event("done", "run_summary", f"執行摘要：{result.summary_path}", path=str(result.summary_path))
    if summary.status == "complete":
        log_event(
            "done",
            "run_status",
            "抓取狀態：全部必要來源皆符合健康門檻",
            status=summary.status,
        )
    else:
        log_event("warn", "run_status", "抓取狀態：部分來源抓取失敗", status=summary.status)
        for warning in summary.warnings:
            log_event("warn", "source_warning", f"- {warning}", warning=warning)


def _resolve_date_range(args: argparse.Namespace, now: datetime) -> tuple[datetime, datetime]:
    if args.period:
        since, until = _parse_period(args.period, now)
    elif args.since:
        since = _parse_date_start(args.since)
        until = _next_local_midnight(now)
    else:
        days = DEFAULT_DAYS_BACK if args.days is None else args.days
        if days < 0:
            raise SystemExit("[error] --days 不可為負數。")
        local_today = now.astimezone(LOCAL_TIMEZONE).date()
        since = _local_midnight(local_today - timedelta(days=days))
        until = _local_midnight(local_today + timedelta(days=1))

    if args.until:
        until = _parse_date_end_exclusive(args.until)

    if until and since >= until:
        raise SystemExit("[error] 日期區間錯誤：起始日期必須早於或等於結束日期。")

    return since, until


def _parse_period(parts: list[str], now: datetime) -> tuple[datetime, datetime]:
    value = _normalize_period("".join(parts))
    if not value:
        local_today = now.astimezone(LOCAL_TIMEZONE).date()
        return (
            _local_midnight(local_today - timedelta(days=DEFAULT_DAYS_BACK)),
            _local_midnight(local_today + timedelta(days=1)),
        )

    if re.fullmatch(r"\d{1,4}", value):
        days = int(value)
        local_today = now.astimezone(LOCAL_TIMEZONE).date()
        return (
            _local_midnight(local_today - timedelta(days=days)),
            _local_midnight(local_today + timedelta(days=1)),
        )

    range_match = re.fullmatch(r"(.+?)[~～〜](.+)", value)
    if range_match:
        start_text, end_text = range_match.groups()
        return _parse_date_start(start_text), _parse_date_end_exclusive(end_text)

    return _parse_date_start(value), _next_local_midnight(now)


def _normalize_period(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", value.strip())


def _parse_date_start(value: str) -> datetime:
    return _local_midnight(_parse_date(value))


def _parse_date_end_exclusive(value: str) -> datetime:
    return _local_midnight(_parse_date(value) + timedelta(days=1))


def _parse_date(value: str) -> date:
    normalized = _normalize_period(value)
    if re.fullmatch(r"\d{8}", normalized):
        return datetime.strptime(normalized, "%Y%m%d").date()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return date.fromisoformat(normalized)
    raise SystemExit(
        f"[error] 無法解析日期參數：{value}。請使用 30、20160501 或 20160501～20160515。"
    )


def _filter_until(items, until: datetime | None):
    if until is None:
        return items
    return [item for item in items if item.published_at < until]


def _date_range_label(since: datetime, until: datetime | None, now: datetime) -> str:
    start_label = _local_date(since).isoformat().replace("-", "")
    if until:
        end_date = _local_date(until - timedelta(microseconds=1))
    else:
        end_date = _local_date(now)
    end_label = end_date.isoformat().replace("-", "")
    return f"{start_label}-{end_label}"


def _require_password_after_trial(now: datetime, marker_path: Path | None = None) -> None:
    marker = marker_path or (Path(DEFAULT_OUTPUT_DIR).parent / FIRST_RUN_FILENAME)
    if not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(now.date().isoformat(), encoding="utf-8")
        return

    try:
        first_run = date.fromisoformat(marker.read_text(encoding="utf-8").strip())
    except ValueError:
        first_run = now.date()
        marker.write_text(first_run.isoformat(), encoding="utf-8")

    if now.date() - first_run <= timedelta(days=PASSWORD_REQUIRED_AFTER_DAYS):
        return

    password = input(f"程式已使用超過 {PASSWORD_REQUIRED_AFTER_DAYS} 天，請輸入密碼：").strip()
    expected_password = os.environ.get("UK_NEWS_RUN_PASSWORD")
    if not expected_password:
        raise SystemExit("[error] 保護版需要設定 UK_NEWS_RUN_PASSWORD 環境變數。")
    if not hmac.compare_digest(password, expected_password):
        raise SystemExit("[error] 密碼錯誤，程式已停止執行。")


def _local_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=LOCAL_TIMEZONE).astimezone(timezone.utc)


def _next_local_midnight(now: datetime) -> datetime:
    local_today = now.astimezone(LOCAL_TIMEZONE).date()
    return _local_midnight(local_today + timedelta(days=1))


def _local_date(value: datetime) -> date:
    return value.astimezone(LOCAL_TIMEZONE).date()


def _run_status(fetch_result, parliament_result) -> tuple[str, list[str]]:
    return evaluate_run_status(fetch_result, parliament_result)


if __name__ == "__main__":
    main()
