from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock, Semaphore, local
from time import monotonic, sleep
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import DEFAULT_RETRY_TOTAL, DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from ..errors import DownloadError, ParseError
from ..models import EndpointObservation

_THREAD_LOCAL = local()
_HOST_LOCK = Lock()
_HOST_SLOTS: dict[str, Semaphore] = {}
MAX_REQUESTS_PER_HOST = 2


@contextmanager
def trace_requests() -> Iterator[list[EndpointObservation]]:
    previous = getattr(_THREAD_LOCAL, "observations", None)
    observations: list[EndpointObservation] = []
    _THREAD_LOCAL.observations = observations
    try:
        yield observations
    finally:
        _THREAD_LOCAL.observations = previous


@contextmanager
def request_deadline(deadline: float | None) -> Iterator[None]:
    previous = getattr(_THREAD_LOCAL, "deadline", None)
    _THREAD_LOCAL.deadline = deadline
    try:
        yield
    finally:
        _THREAD_LOCAL.deadline = previous


def current_request_deadline() -> float | None:
    return cast(float | None, getattr(_THREAD_LOCAL, "deadline", None))


def _remaining(timeout: float) -> float:
    deadline = current_request_deadline()
    if deadline is None:
        return timeout
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DownloadError("本次抓取已達整體等待上限")
    return min(timeout, remaining)


def _host_slot(url: str) -> Semaphore:
    host = (urlsplit(url).hostname or "").lower()
    with _HOST_LOCK:
        return _HOST_SLOTS.setdefault(host, Semaphore(MAX_REQUESTS_PER_HOST))


def _retry_after(response: requests.Response) -> float:
    raw = response.headers.get("Retry-After", "").strip()
    if not raw:
        return 1.0
    if raw.isdecimal():
        return float(raw)
    try:
        return max(0.0, (parsedate_to_datetime(raw) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return 1.0


def _request(url: str, *, timeout: float, headers: dict[str, str]) -> requests.Response:
    slot = _host_slot(url)
    for attempt in range(2):
        wait = _remaining(timeout)
        if not slot.acquire(timeout=wait):
            raise DownloadError(f"同網域請求等待逾時：{url}")
        try:
            response = get_session().get(url, timeout=_remaining(timeout), headers=headers)
        except requests.RequestException as exc:
            _observe(url, exc.response)
            raise
        finally:
            slot.release()
        _observe(url, response)
        if response.status_code not in {429, 503} or attempt == 1:
            return response
        delay = _retry_after(response)
        response.close()
        deadline = getattr(_THREAD_LOCAL, "deadline", None)
        if deadline is not None and delay >= deadline - monotonic():
            raise DownloadError(f"伺服器要求延後重試，已保留現有資料：{url}")
        if delay > timeout:
            return response
        sleep(delay)
    raise AssertionError("bounded request loop exhausted")


def _observe(url: str, response: requests.Response | None) -> None:
    observations = getattr(_THREAD_LOCAL, "observations", None)
    if observations is None:
        return
    parts = urlsplit(url)
    endpoint = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    body = response.content if response is not None else b""
    observations.append(
        EndpointObservation(
            url=endpoint,
            status_code=response.status_code if response is not None else 0,
            fetched_at=datetime.now(UTC).isoformat(),
            response_sha256=hashlib.sha256(body).hexdigest() if response is not None else "",
            etag=response.headers.get("ETag", "") if response is not None else "",
            last_modified=response.headers.get("Last-Modified", "") if response is not None else "",
            bytes_count=len(body),
        )
    )


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=DEFAULT_RETRY_TOTAL,
        connect=DEFAULT_RETRY_TOTAL,
        read=DEFAULT_RETRY_TOTAL,
        status=DEFAULT_RETRY_TOTAL,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = _build_session()
        _THREAD_LOCAL.session = session
    return session


def get_text(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    try:
        response = _request(url, timeout=timeout, headers=_headers())
    except requests.RequestException as exc:
        raise DownloadError(f"download failed: {url}") from exc
    if response.status_code == 403 and _looks_like_cloudflare_challenge(response.text):
        return _get_text_with_browser_tls(url, timeout)
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DownloadError(f"download failed: {url}") from exc
    return response.text


def get_json(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
) -> Any:
    request_headers = _headers()
    request_headers["Accept"] = "application/json"
    if headers:
        request_headers.update(headers)
    response = _request(url, timeout=timeout, headers=request_headers)
    response.raise_for_status()
    try:
        return response.json()
    except requests.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON response: {url}") from exc


def _headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml, text/html;q=0.9, */*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }


def _looks_like_cloudflare_challenge(text: str) -> bool:
    lowered = text[:10000].lower()
    return "just a moment" in lowered and "cloudflare" in lowered


def _get_text_with_browser_tls(url: str, timeout: int) -> str:
    try:
        from curl_cffi import requests as curl_requests
    except ImportError as exc:
        raise requests.HTTPError(f"403 Forbidden and curl_cffi is not installed for browser-like retry: {url}") from exc

    slot = _host_slot(url)
    if not slot.acquire(timeout=_remaining(timeout)):
        raise DownloadError(f"同網域請求等待逾時：{url}")
    try:
        response = curl_requests.get(
            url,
            timeout=_remaining(timeout),
            impersonate="chrome120",
            headers={
                "Accept": _headers()["Accept"],
                "Accept-Language": _headers()["Accept-Language"],
            },
        )
    finally:
        slot.release()
    _observe(url, cast(requests.Response, response))
    if response.status_code == 403 and _looks_like_cloudflare_challenge(response.text):
        raise requests.HTTPError(f"403 Forbidden Cloudflare challenge: {url}")
    response.raise_for_status()  # type: ignore[no-untyped-call]
    return response.text
