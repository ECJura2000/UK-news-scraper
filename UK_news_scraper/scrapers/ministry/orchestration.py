from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from time import monotonic, sleep

from ...config import DEFAULT_MAX_WORKERS
from ...errors import UKNewsError, is_retryable_error
from .registry import build_scrapers, dedupe_items
from .status import AgencyFetchStatus, FetchAllResult, health_warning, newest_published_at


RETRY_DELAY_SECONDS = 2


def fetch_all_with_status(since: datetime, max_workers: int = DEFAULT_MAX_WORKERS) -> FetchAllResult:
    all_items = []
    statuses = []
    scrapers = build_scrapers()
    workers = max(1, min(max_workers, len(scrapers)))
    failed_scrapers = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(scraper.fetch, since): (scraper, monotonic()) for scraper in scrapers}
        for future in as_completed(future_map):
            scraper, started_at = future_map[future]
            duration = monotonic() - started_at
            try:
                items = future.result()
            except (UKNewsError, OSError, ValueError, KeyError, TypeError) as exc:
                if is_retryable_error(exc):
                    failed_scrapers.append((scraper, str(exc), duration))
                else:
                    statuses.append(_failed_status(scraper, str(exc), duration, attempts=1))
                continue
            statuses.append(_success_status(scraper, items, since, duration, attempts=1))
            all_items.extend(items)

    if failed_scrapers:
        sleep(RETRY_DELAY_SECONDS)
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(failed_scrapers)))) as executor:
            future_map = {
                executor.submit(scraper.fetch, since): (scraper, first_error, first_duration, monotonic())
                for scraper, first_error, first_duration in failed_scrapers
            }
            for future in as_completed(future_map):
                scraper, first_error, first_duration, started_at = future_map[future]
                duration = first_duration + monotonic() - started_at
                try:
                    items = future.result()
                except (UKNewsError, OSError, ValueError, KeyError, TypeError) as exc:
                    statuses.append(_failed_status(scraper, f"首次：{first_error}；重試：{exc}", duration, attempts=2))
                    continue
                statuses.append(_success_status(scraper, items, since, duration, attempts=2))
                all_items.extend(items)
    return FetchAllResult(items=dedupe_items(all_items), statuses=statuses)


def fetch_all(since: datetime, max_workers: int = DEFAULT_MAX_WORKERS):
    return fetch_all_with_status(since, max_workers=max_workers).items


def _success_status(scraper, items, since, duration, attempts):
    return AgencyFetchStatus(
        agency_name=scraper.agency.display_name,
        source_name=scraper.agency.short_name,
        success=True,
        item_count=len(items),
        attempts=attempts,
        duration_seconds=duration,
        newest_published_at=newest_published_at(items),
        warning=health_warning(scraper.agency.short_name, items, since),
    )


def _failed_status(scraper, error, duration, attempts):
    return AgencyFetchStatus(
        agency_name=scraper.agency.display_name,
        source_name=scraper.agency.short_name,
        success=False,
        attempts=attempts,
        error=error,
        duration_seconds=duration,
    )
