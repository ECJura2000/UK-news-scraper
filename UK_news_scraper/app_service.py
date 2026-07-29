from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .calendar_utils import CalendarMode, output_filename
from .config import AGENCIES, DEFAULT_MAX_WORKERS, DEFAULT_OUTPUT_DIR, DEFAULT_TIMEZONE
from .dedupe import dedupe_news_items
from .excel_exporter import ExportOptions, export_news
from .models import NewsItem, ParliamentBriefing, RunStatus
from .profiles import (
    DEFAULT_PROFILE_ID,
    PARLIAMENT_SOURCE_ID,
    FilterProfile,
    default_profile,
    profile_hash,
)
from .run_summary import (
    RunSummary,
    make_data_fingerprint,
    make_delivery_id,
    make_run_id,
    write_run_summary,
)
from .runtime_lock import exclusive_lock
from .scrapers.ministry.orchestration import fetch_all_with_status
from .scrapers.ministry.registry import apply_parliament_topic_filter, apply_topic_filter
from .scrapers.parliament import ParliamentFetchResult, fetch_parliament_briefings


ProgressCallback = Callable[["ProgressEvent"], None]
CancelCallback = Callable[[], bool]
LOCAL_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)


class RunCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    message: str
    current: int = 0
    total: int = 0
    source: str = ""
    level: str = "info"


@dataclass(frozen=True)
class ExportOptionsRequest:
    calendar_mode: CalendarMode = CalendarMode.GREGORIAN


@dataclass(frozen=True)
class RunRequest:
    period_start: date
    period_end: date
    output_path: Path | None = None
    output_dir: Path = Path(DEFAULT_OUTPUT_DIR)
    workers: int = DEFAULT_MAX_WORKERS
    profile: FilterProfile | None = None
    export_options: ExportOptionsRequest = ExportOptionsRequest()
    retry_source_ids: tuple[str, ...] = ()
    base_result: RunResult | None = None


@dataclass(frozen=True)
class RunResult:
    workbook_path: Path
    summary_path: Path
    summary: RunSummary
    all_items: tuple[NewsItem, ...]
    filtered_items: tuple[NewsItem, ...]
    parliament_items: tuple[ParliamentBriefing, ...]
    filtered_parliament_items: tuple[ParliamentBriefing, ...]


def execute_run(
    request: RunRequest,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> RunResult:
    if request.period_end < request.period_start:
        raise ValueError("結束日期不得早於開始日期")
    if request.workers < 1:
        raise ValueError("worker 數必須大於等於 1")
    _check_cancelled(cancelled)

    active_profile = request.profile or default_profile()
    retry_source_ids = set(request.retry_source_ids)
    if retry_source_ids and request.base_result is None:
        raise ValueError("重試異常來源需要前次執行結果")
    if retry_source_ids - set(active_profile.selected_sources):
        raise ValueError("重試來源必須包含在目前設定檔中")
    selected_source_ids = retry_source_ids or set(active_profile.selected_sources)
    selected_agencies = tuple(
        agency for agency in AGENCIES if agency.short_name in selected_source_ids
    )
    include_parliament = PARLIAMENT_SOURCE_ID in selected_source_ids
    since = _local_midnight(request.period_start)
    until = _local_midnight(request.period_end + timedelta(days=1))
    base_run_id = make_run_id(request.period_start, request.period_end)
    run_id = (
        base_run_id
        if active_profile.profile_id == DEFAULT_PROFILE_ID
        else f"{base_run_id}-{active_profile.profile_id}"
    )
    output = request.output_path or (
        request.output_dir
        / output_filename(
            request.period_start,
            request.period_end,
            active_profile.profile_id,
            default_profile_id=DEFAULT_PROFILE_ID,
        )
    )
    output = Path(output).expanduser().resolve()
    lock_path = output.parent / f".{run_id}.lock"

    with exclusive_lock(lock_path):
        action = "重新抓取異常來源" if retry_source_ids else "抓取已選取的 UK 新聞來源"
        _emit(progress, "fetch_news", f"正在{action}", 1, 5)
        fetch_result = fetch_all_with_status(
            since,
            max_workers=request.workers,
            agencies=selected_agencies,
        )
        _check_cancelled(cancelled)
        fetched_items = _filter_until(fetch_result.items, until)
        all_items = _merge_news_items(
            request.base_result,
            fetched_items,
            retry_source_ids,
        )

        _emit(progress, "filter_news", "正在套用主題與關鍵詞設定", 2, 5)
        filtered_items = apply_topic_filter(all_items, active_profile)
        _check_cancelled(cancelled)

        if include_parliament:
            _emit(progress, "fetch_parliament", "正在抓取 UK Parliament 研究資料", 3, 5)
            parliament_result = fetch_parliament_briefings(since)
            fetched_parliament_items = _filter_until(parliament_result.items, until)
        else:
            parliament_result = ParliamentFetchResult(
                items=[],
                source_mode="未選取",
            )
            fetched_parliament_items = []
        _check_cancelled(cancelled)
        parliament_items = _merge_parliament_items(
            request.base_result,
            fetched_parliament_items,
            retry_source_ids,
            include_parliament,
        )
        filtered_parliament_items = apply_parliament_topic_filter(
            parliament_items,
            active_profile,
        )

        _check_cancelled(cancelled)
        _emit(progress, "export", "正在翻譯並建立 Excel", 4, 5)
        path = export_news(
            all_items,
            filtered_items,
            output,
            parliament_items=parliament_items,
            filtered_parliament_items=filtered_parliament_items,
            export_options=ExportOptions(
                calendar_mode=request.export_options.calendar_mode,
                profile=active_profile,
            ),
        )
        source_health = _merge_source_health(
            request.base_result,
            fetch_result.source_health,
            parliament_result.source_health,
            retry_source_ids,
        )
        if retry_source_ids:
            status, warnings = evaluate_source_health(source_health)
        else:
            status, warnings = evaluate_run_status(fetch_result, parliament_result)
        data_fingerprint = make_data_fingerprint(all_items, parliament_items)
        delivery_id = make_delivery_id(run_id, status, data_fingerprint)
        summary = RunSummary(
            run_id=run_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period_start=request.period_start.isoformat(),
            period_end=request.period_end.isoformat(),
            output_file=str(path),
            all_news_count=len(all_items),
            filtered_news_count=len(filtered_items),
            parliament_count=len(parliament_items),
            filtered_parliament_count=len(filtered_parliament_items),
            status=status,
            warnings=tuple(warnings),
            data_fingerprint=data_fingerprint,
            delivery_id=delivery_id,
            source_health=source_health,
            profile_id=active_profile.profile_id,
            profile_name=active_profile.name,
            profile_version=active_profile.version,
            profile_hash=profile_hash(active_profile),
            selected_sources=active_profile.selected_sources,
            minimum_score=active_profile.minimum_score,
            excel_date_calendar=request.export_options.calendar_mode.value,
        )
        summary_path = write_run_summary(summary, path)
        _emit(progress, "done", "抓取與 Excel 匯出完成", 5, 5)
        return RunResult(
            workbook_path=path,
            summary_path=summary_path,
            summary=summary,
            all_items=tuple(all_items),
            filtered_items=tuple(filtered_items),
            parliament_items=tuple(parliament_items),
            filtered_parliament_items=tuple(filtered_parliament_items),
        )


def evaluate_run_status(fetch_result, parliament_result) -> tuple[RunStatus, list[str]]:
    warnings = [
        f"{status.agency_name}：{status.error}"
        for status in fetch_result.failed_statuses
    ]
    warnings.extend(parliament_result.warnings)
    warnings.extend(
        health.warning
        for health in fetch_result.source_health + parliament_result.source_health
        if health.success and health.warning and health.warning not in warnings
    )
    if fetch_result.all_successful and parliament_result.all_successful:
        return RunStatus.COMPLETE, warnings
    return RunStatus.DEGRADED, warnings


def evaluate_source_health(source_health) -> tuple[RunStatus, list[str]]:
    warnings = [health.warning for health in source_health if health.warning]
    if all(health.success and not health.warning for health in source_health):
        return RunStatus.COMPLETE, warnings
    return RunStatus.DEGRADED, warnings


def _merge_news_items(
    base_result: RunResult | None,
    fetched_items: list[NewsItem],
    retry_source_ids: set[str],
) -> list[NewsItem]:
    if not retry_source_ids or base_result is None:
        return dedupe_news_items(fetched_items)
    preserved = [
        item
        for item in base_result.all_items
        if _news_source_id(item) not in retry_source_ids
    ]
    return dedupe_news_items([*preserved, *fetched_items])


def _merge_parliament_items(
    base_result: RunResult | None,
    fetched_items: list[ParliamentBriefing],
    retry_source_ids: set[str],
    include_parliament: bool,
) -> list[ParliamentBriefing]:
    if not retry_source_ids or base_result is None:
        return fetched_items
    if include_parliament:
        return fetched_items
    return list(base_result.parliament_items)


def _merge_source_health(
    base_result: RunResult | None,
    news_health,
    parliament_health,
    retry_source_ids: set[str],
):
    current = list(news_health) + list(parliament_health)
    if not retry_source_ids or base_result is None:
        return tuple(current)
    preserved = [
        health
        for health in base_result.summary.source_health
        if _health_source_id(health.source) not in retry_source_ids
    ]
    combined = [*preserved, *current]
    order = {
        source: index
        for index, source in enumerate(
            [agency.short_name for agency in AGENCIES] + [PARLIAMENT_SOURCE_ID]
        )
    }
    return tuple(
        sorted(
            combined,
            key=lambda health: order.get(
                _health_source_id(health.source),
                len(order),
            ),
        )
    )


def _news_source_id(item: NewsItem) -> str:
    for agency in AGENCIES:
        if (
            item.agency == agency.display_name
            or item.agency == agency.short_name
            or item.agency_en == agency.name_en
            or item.unit_category == agency.short_name
        ):
            return agency.short_name
    return item.agency


def _health_source_id(source: str) -> str:
    agency_ids = {agency.short_name for agency in AGENCIES}
    return source if source in agency_ids else PARLIAMENT_SOURCE_ID


def _check_cancelled(callback: CancelCallback | None) -> None:
    if callback and callback():
        raise RunCancelled("使用者已取消本次執行")


def _filter_until(items, until: datetime):
    return [item for item in items if item.published_at < until]


def _local_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=LOCAL_TIMEZONE).astimezone(timezone.utc)


def _emit(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
    current: int,
    total: int,
) -> None:
    if callback:
        callback(
            ProgressEvent(
                stage=stage,
                message=message,
                current=current,
                total=total,
            )
        )
