from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from time import monotonic, sleep

from ...config import AGENCIES, DEFAULT_MAX_WORKERS
from ...errors import UKNewsError, is_retryable_error
from ...http.async_client import request_deadline, trace_requests
from ...models import Agency, EndpointObservation, NewsItem
from .registry import AgencyFeedScraper, build_scrapers
from .status import AgencyFetchStatus, FetchAllResult, health_warning, newest_published_at
from .utils.dedupe import dedupe_items

RETRY_DELAY_SECONDS = 1


def fetch_all_with_status(
    since: datetime,
    max_workers: int = DEFAULT_MAX_WORKERS,
    agencies: tuple[Agency, ...] | None = None,
    until: datetime | None = None,
    deadline: float | None = None,
) -> FetchAllResult:
    all_items: list[NewsItem] = []
    statuses: list[AgencyFetchStatus] = []
    if until is None:
        scrapers = build_scrapers() if agencies is None else build_scrapers(agencies)
    else:
        scrapers = build_scrapers(AGENCIES if agencies is None else agencies, until=until)
    if not scrapers:
        return FetchAllResult(items=[], statuses=[])
    workers = max(1, min(max_workers, len(scrapers)))
    failed_scrapers: list[tuple[AgencyFeedScraper, str, float, tuple[EndpointObservation, ...]]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_fetch_scraper, scraper, since, deadline): (scraper, monotonic()) for scraper in scrapers
        }
        for future in as_completed(future_map):
            scraper, started_at = future_map[future]
            duration = monotonic() - started_at
            items, endpoints, error = future.result()
            if error is not None:
                exc = error
                if is_retryable_error(exc):
                    failed_scrapers.append((scraper, str(exc), duration, endpoints))
                else:
                    statuses.append(_failed_status(scraper, str(exc), duration, attempts=1, endpoints=endpoints))
                continue
            selected_items = [item for item in items if until is None or item.published_at < until]
            statuses.append(_success_status(scraper, selected_items, since, duration, attempts=1, endpoints=endpoints))
            all_items.extend(selected_items)

    if failed_scrapers:
        if deadline is None or monotonic() + RETRY_DELAY_SECONDS < deadline:
            sleep(RETRY_DELAY_SECONDS)
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(failed_scrapers)))) as executor:
            retry_future_map = {
                executor.submit(_fetch_scraper, scraper, since, deadline): (
                    scraper,
                    first_error,
                    first_duration,
                    first_endpoints,
                    monotonic(),
                )
                for scraper, first_error, first_duration, first_endpoints in failed_scrapers
            }
            for future in as_completed(retry_future_map):
                scraper, first_error, first_duration, first_endpoints, started_at = retry_future_map[future]
                duration = first_duration + monotonic() - started_at
                items, retry_endpoints, error = future.result()
                endpoints = first_endpoints + retry_endpoints
                if error is not None:
                    statuses.append(
                        _failed_status(
                            scraper, f"首次：{first_error}；重試：{error}", duration, attempts=2, endpoints=endpoints
                        )
                    )
                    continue
                selected_items = [item for item in items if until is None or item.published_at < until]
                statuses.append(
                    _success_status(scraper, selected_items, since, duration, attempts=2, endpoints=endpoints)
                )
                all_items.extend(selected_items)
    return FetchAllResult(items=dedupe_items(all_items), statuses=statuses)


def fetch_all(
    since: datetime,
    max_workers: int = DEFAULT_MAX_WORKERS,
    agencies: tuple[Agency, ...] | None = None,
) -> list[NewsItem]:
    return fetch_all_with_status(since, max_workers=max_workers, agencies=agencies).items


def _fetch_scraper(
    scraper: AgencyFeedScraper, since: datetime, deadline: float | None = None
) -> tuple[list[NewsItem], tuple[EndpointObservation, ...], Exception | None]:
    with request_deadline(deadline), trace_requests() as observations:
        try:
            items = scraper.fetch(since)
        except (UKNewsError, OSError, ValueError, KeyError, TypeError) as error:
            return [], tuple(observations), error
        return items, tuple(observations), None


def _success_status(
    scraper: AgencyFeedScraper,
    items: list[NewsItem],
    since: datetime,
    duration: float,
    attempts: int,
    endpoints: tuple[EndpointObservation, ...] = (),
) -> AgencyFetchStatus:
    warnings = list(
        dict.fromkeys(
            warning
            for warning in (health_warning(scraper.agency.short_name, items, since), *scraper.source_warnings)
            if warning
        )
    )
    if (
        getattr(scraper, "candidate_count", 0) > 0
        and not items
        and not any("解析為零筆" in warning for warning in warnings)
    ):
        warnings.append(f"{scraper.agency.short_name} 有候選資料但解析為零筆")
    return AgencyFetchStatus(
        agency_name=scraper.agency.display_name,
        source_name=scraper.agency.short_name,
        success=True,
        item_count=len(items),
        attempts=attempts,
        duration_seconds=duration,
        newest_published_at=newest_published_at(items),
        warning="；".join(warnings),
        candidate_count=getattr(scraper, "candidate_count", 0),
        fetched_at=endpoints[-1].fetched_at if endpoints else datetime.now(UTC).isoformat(),
        endpoints=endpoints,
    )


def _failed_status(
    scraper: AgencyFeedScraper,
    error: str,
    duration: float,
    attempts: int,
    endpoints: tuple[EndpointObservation, ...] = (),
) -> AgencyFetchStatus:
    return AgencyFetchStatus(
        agency_name=scraper.agency.display_name,
        source_name=scraper.agency.short_name,
        success=False,
        attempts=attempts,
        error=error,
        duration_seconds=duration,
        candidate_count=getattr(scraper, "candidate_count", 0),
        fetched_at=endpoints[-1].fetched_at if endpoints else datetime.now(UTC).isoformat(),
        endpoints=endpoints,
    )
