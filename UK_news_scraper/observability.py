OBSERVABILITY_BUDGETS = {
    "minimum_source_success_rate": 0.90,
    "source_p95_seconds": 60.0,
    "maximum_zero_item_ratio": 0.25,
    "benchmark_peak_memory_mb_100k": 30.0,
}


def evaluate_observability_budget(*, success_rate: float, p95_seconds: float, zero_item_ratio: float, peak_memory_mb: float):
    warnings = []
    if success_rate < OBSERVABILITY_BUDGETS["minimum_source_success_rate"]:
        warnings.append("source_success_rate")
    if p95_seconds > OBSERVABILITY_BUDGETS["source_p95_seconds"]:
        warnings.append("source_p95_seconds")
    if zero_item_ratio > OBSERVABILITY_BUDGETS["maximum_zero_item_ratio"]:
        warnings.append("zero_item_ratio")
    if peak_memory_mb > OBSERVABILITY_BUDGETS["benchmark_peak_memory_mb_100k"]:
        warnings.append("peak_memory_mb_100k")
    return warnings
