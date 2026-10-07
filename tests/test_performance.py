import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from UK_news_scraper.performance import (
    _CURRENT,
    Recorder,
    current_recorder,
    http_attempt,
    http_status,
    measure,
    route_category,
    submit,
)
from UK_news_scraper.run_summary import RunSummary, make_delivery_id, validate_run_summary_payload, write_run_summary


def test_worker_context_is_run_local_and_counts_transport_attempts():
    first, second = Recorder("full"), Recorder("retry")
    with ThreadPoolExecutor(max_workers=2) as executor:

        def request():
            with measure("dedupe_work_seconds"):
                http_attempt("search_api")
                http_status("search_api", 429)
                http_attempt("search_api", retry=True)
                http_status("search_api", 200)

        token = _CURRENT.set(first)
        future = submit(executor, request)
        _CURRENT.reset(token)
        token = _CURRENT.set(second)
        other = submit(executor, request)
        _CURRENT.reset(token)
        future.result()
        other.result()
    assert current_recorder() is None
    for recorder in (first, second):
        assert asdict(recorder.data.http["search_api"]) == {
            "attempted_count": 2,
            "retry_count": 1,
            "rate_limited_count": 1,
        }
        assert recorder.data.stages["dedupe_work_seconds"] >= 0
    # Calls outside a run never contaminate later runs.
    http_attempt("list")
    http_status("list", 429)
    assert first.data.http["list"].attempted_count == 0


@pytest.mark.parametrize(
    ("url", "category"),
    [
        ("https://news.google.com/rss/search?q=x", "fallback"),
        ("https://www.gov.uk/api/search.json?q=x", "search_api"),
        ("https://lda.data.parliament.uk/researchbriefings.json", "search_api"),
        ("https://example.org/feed", "list"),
    ],
)
def test_request_categories(url, category):
    assert route_category(url) == category


def test_summary_is_additive_and_does_not_change_delivery_identity(tmp_path):
    old = dict(
        run_id="run",
        generated_at="now",
        period_start="2026-10-01",
        period_end="2026-10-07",
        output_file=str(tmp_path / "report.xlsx"),
        all_news_count=0,
        filtered_news_count=0,
        parliament_count=0,
        filtered_parliament_count=0,
        status="complete",
        warnings=(),
        data_fingerprint="a" * 64,
        delivery_id=make_delivery_id("run", "complete", "a" * 64),
        source_health=(),
    )
    assert validate_run_summary_payload(old) is old
    legacy = RunSummary(**old)
    updated = replace(legacy, performance=Recorder("retry").data)
    payload = json.loads(write_run_summary(updated, old["output_file"]).read_text())
    assert validate_run_summary_payload(payload) == payload
    assert payload["delivery_id"] == legacy.delivery_id
    assert payload["data_fingerprint"] == legacy.data_fingerprint
    assert payload["performance"]["run_kind"] == "retry"
    assert payload["performance"]["counts"] == {}
    assert payload["performance"]["detail_fetch_enabled"] is False
    assert payload["performance"]["stages"]["json_write_seconds"] is None


def test_translation_hooks_count_http_not_jobs_or_cache(monkeypatch):
    from UK_news_scraper.translation_service import translate_titles_async

    class Translator:
        def __init__(self):
            self.client = SimpleNamespace(event_hooks={})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def translate(self, title, **kwargs):
            for hook in self.client.event_hooks["request"]:
                await hook(SimpleNamespace())
            for hook in self.client.event_hooks["response"]:
                await hook(SimpleNamespace(status_code=429))
            raise RuntimeError("rate limited")

    recorder = Recorder("full")
    token = _CURRENT.set(recorder)
    try:
        result = asyncio.run(
            translate_titles_async(
                ["AI policy"],
                Translator,
                "test",
                concurrency=1,
                request_timeout=1,
                budget=2,
            )
        )
    finally:
        _CURRENT.reset(token)
    assert result == {"AI policy": ""}
    assert recorder.data.http["translation"].attempted_count == 1
    assert recorder.data.http["translation"].rate_limited_count == 1


def test_transport_counters_include_failure_and_retry(monkeypatch):
    import requests

    from UK_news_scraper.http import async_client

    responses = iter(
        [
            SimpleNamespace(status_code=429, headers={"Retry-After": "0"}, close=lambda: None),
            SimpleNamespace(status_code=200, headers={}, close=lambda: None),
        ]
    )
    monkeypatch.setattr(async_client, "get_session", lambda: SimpleNamespace(get=lambda *a, **k: next(responses)))
    recorder = Recorder("full")
    token = _CURRENT.set(recorder)
    try:
        assert async_client._request("https://www.gov.uk/api/search.json", timeout=1, headers={}).status_code == 200

        def offline(*args, **kwargs):
            raise requests.ConnectionError("offline")

        monkeypatch.setattr(async_client, "get_session", lambda: SimpleNamespace(get=offline))
        with pytest.raises(requests.ConnectionError):
            async_client._request("https://example.org/feed", timeout=1, headers={})
    finally:
        _CURRENT.reset(token)
    assert recorder.data.http["search_api"].attempted_count == 2
    assert recorder.data.http["search_api"].retry_count == 1
    assert recorder.data.http["search_api"].rate_limited_count == 1
    assert recorder.data.http["list"].attempted_count == 1
