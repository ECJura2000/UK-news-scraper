from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil

from .models import SourceHealth

OBSERVABILITY_BUDGETS = {
    "minimum_source_success_rate": 0.90,
    "source_p95_seconds": 60.0,
    "maximum_zero_item_ratio": 0.25,
    "benchmark_peak_memory_mb_100k": 30.0,
}


def evaluate_observability_budget(
    *, success_rate: float, p95_seconds: float, zero_item_ratio: float, peak_memory_mb: float
) -> list[str]:
    warnings: list[str] = []
    if success_rate < OBSERVABILITY_BUDGETS["minimum_source_success_rate"]:
        warnings.append("source_success_rate")
    if p95_seconds > OBSERVABILITY_BUDGETS["source_p95_seconds"]:
        warnings.append("source_p95_seconds")
    if zero_item_ratio > OBSERVABILITY_BUDGETS["maximum_zero_item_ratio"]:
        warnings.append("zero_item_ratio")
    if peak_memory_mb > OBSERVABILITY_BUDGETS["benchmark_peak_memory_mb_100k"]:
        warnings.append("peak_memory_mb_100k")
    return warnings


@dataclass(frozen=True)
class RunObservability:
    source_count: int = 0
    source_success_rate: float = 1.0
    source_p95_seconds: float = 0.0
    zero_item_ratio: float = 0.0
    alerts: tuple[str, ...] = ()


def summarize_source_health(source_health: Iterable[SourceHealth]) -> RunObservability:
    """Report budgets on every run; an empty source is diagnostic, not a failed scrape."""
    sources = tuple(source for source in source_health if source.critical)
    if not sources:
        return RunObservability()
    count = len(sources)
    success_rate = sum(source.success for source in sources) / count
    zero_ratio = sum(source.item_count == 0 for source in sources) / count
    durations = sorted(source.duration_seconds for source in sources)
    p95 = durations[ceil(count * 0.95) - 1]
    alerts = evaluate_observability_budget(
        success_rate=success_rate,
        p95_seconds=p95,
        zero_item_ratio=zero_ratio,
        peak_memory_mb=0.0,
    )
    return RunObservability(
        source_count=count,
        source_success_rate=round(success_rate, 3),
        source_p95_seconds=round(p95, 3),
        zero_item_ratio=round(zero_ratio, 3),
        alerts=tuple(alerts),
    )
