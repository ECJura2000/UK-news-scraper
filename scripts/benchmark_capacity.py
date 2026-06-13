from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from UK_news_scraper.dedupe import dedupe_news_items
from UK_news_scraper.models import NewsItem


def percentile(samples: list[float], p: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))]


def measure(operation, iterations: int = 5) -> dict:
    operation()
    samples, peaks = [], []
    for _ in range(iterations):
        tracemalloc.start()
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak / 1024 / 1024)
    return {
        "best_ms": round(min(samples), 3),
        "mean_ms": round(statistics.fmean(samples), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "peak_memory_mb": round(max(peaks), 3),
    }


def make_items(size: int):
    return [
        NewsItem("Agency", "Agency", "A", f"Title {index // 2}", f"https://example.com/{index // 2}", datetime.now(timezone.utc))
        for index in range(size)
    ]


def concurrency_measure(workers: int, jobs: int = 64) -> dict:
    def task(index):
        time.sleep(0.002)
        return index

    return measure(lambda: list(ThreadPoolExecutor(max_workers=workers).map(task, range(jobs))), iterations=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 100000])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 4, 6, 13])
    args = parser.parse_args()
    print(json.dumps({
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "dedupe": {str(size): measure(lambda items=make_items(size): dedupe_news_items(items)) for size in args.sizes},
        "concurrency": {str(workers): concurrency_measure(workers) for workers in args.workers},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
