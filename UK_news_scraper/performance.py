"""Run-scoped diagnostics; never part of record identity or delivery state."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Executor, Future
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import urlsplit


@dataclass
class HttpCounts:
    attempted_count: int = 0
    retry_count: int = 0
    rate_limited_count: int = 0


@dataclass
class PipelineCounts:
    # Existing parser health candidates are in-period and may include malformed
    # records. Raw list totals are not available consistently across adapters.
    list_items_count: int | None = None
    candidate_count: int = 0
    source_output_count: int = 0
    date_filtered_count: int = 0
    deduped_count: int = 0
    final_output_count: int = 0
    relevant_output_count: int = 0


@dataclass
class RunPerformance:
    schema_version: int = 1
    runtime: str = "python"
    runtime_version: str = ""
    workers: int = 0
    translation_cache_hits: int = 0
    translation_cache_misses: int = 0
    run_kind: str = "full"
    total_wall_seconds: float = 0.0
    total_endpoint: str = "before_summary_serialization"
    detail_fetch_enabled: bool = False
    stages: dict[str, float | None] = field(
        default_factory=lambda: {
            "collection_wall_seconds": 0.0,
            "dedupe_work_seconds": 0.0,
            "relevance_seconds": 0.0,
            "translation_seconds": 0.0,
            "excel_write_seconds": 0.0,
            "json_write_seconds": None,
        }
    )
    counts: dict[str, PipelineCounts] = field(default_factory=dict)
    http: dict[str, HttpCounts] = field(
        default_factory=lambda: {name: HttpCounts() for name in ("list", "search_api", "fallback", "translation")}
    )


class Recorder:
    def __init__(self, run_kind: str) -> None:
        self.started = monotonic()
        self.data = RunPerformance(run_kind=run_kind)
        self.lock = Lock()

    def duration(self, name: str, elapsed: float) -> None:
        with self.lock:
            self.data.stages[name] = (self.data.stages.get(name) or 0.0) + max(0.0, elapsed)


_CURRENT: ContextVar[Recorder | None] = ContextVar("uk_run_performance", default=None)


def current_recorder() -> Recorder | None:
    return _CURRENT.get()


@contextmanager
def measure(name: str) -> Iterator[None]:
    started = monotonic()
    try:
        yield
    finally:
        if recorder := current_recorder():
            recorder.duration(name, monotonic() - started)


def timed[**P, R](name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with measure(name):
                return fn(*args, **kwargs)

        return wrapped

    return decorate


def measured_run[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        from . import __version__

        request: Any = args[0] if args else kwargs["request"]

        recorder = Recorder("retry" if request.retry_source_ids else "full")
        recorder.data.runtime_version = __version__
        recorder.data.workers = request.workers
        token = _CURRENT.set(recorder)
        try:
            result = fn(*args, **kwargs)
            print(f"[performance] artifacts_complete_seconds={monotonic() - recorder.started:.6f}")
            return result
        finally:
            _CURRENT.reset(token)

    return wrapped


def submit[**P, R](executor: Executor, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> Future[R]:
    # Each submission needs its own Context; a Context cannot run concurrently.
    context = copy_context()

    def invoke() -> R:
        return context.run(fn, *args, **kwargs)

    return executor.submit(invoke)


def route_category(url: str) -> str:
    parts = urlsplit(url)
    if parts.hostname == "news.google.com":
        return "fallback"
    if parts.path.endswith("/api/search.json") or "researchbriefings.json" in parts.path:
        return "search_api"
    return "list"


def http_attempt(category: str, retry: bool = False) -> None:
    if recorder := current_recorder():
        with recorder.lock:
            counts = recorder.data.http[category]
            counts.attempted_count += 1
            counts.retry_count += int(retry)


def http_status(category: str, status: int) -> None:
    if status == 429 and (recorder := current_recorder()):
        with recorder.lock:
            recorder.data.http[category].rate_limited_count += 1
