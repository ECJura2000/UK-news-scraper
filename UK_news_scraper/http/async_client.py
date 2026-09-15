from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from threading import local
from typing import Any
from urllib3.util.retry import Retry

from ..config import DEFAULT_RETRY_TOTAL, DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from ..errors import DownloadError, ParseError


_THREAD_LOCAL = local()


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
        response = get_session().get(url, timeout=timeout, headers=_headers())
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
    response = get_session().get(url, timeout=timeout, headers=request_headers)
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
    except ImportError:
        raise requests.HTTPError(
            f"403 Forbidden and curl_cffi is not installed for browser-like retry: {url}"
        )

    response = curl_requests.get(
        url,
        timeout=timeout,
        impersonate="chrome120",
        headers={
            "Accept": _headers()["Accept"],
            "Accept-Language": _headers()["Accept-Language"],
        },
    )
    if response.status_code == 403 and _looks_like_cloudflare_challenge(response.text):
        raise requests.HTTPError(f"403 Forbidden Cloudflare challenge: {url}")
    response.raise_for_status()
    return response.text
