import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from UK_news_scraper.delivery_registry import claim_delivery, complete_delivery, release_delivery
from UK_news_scraper.runtime_lock import LockUnavailable, exclusive_lock


def _summary(path, delivery_id="delivery-1"):
    path.write_text(
        json.dumps(
            {
                "delivery_id": delivery_id,
                "run_id": "run-1",
                "status": "complete",
                "data_fingerprint": "abc",
                "output_file": "/tmp/report.xlsx",
            }
        ),
        encoding="utf-8",
    )


def test_only_one_concurrent_delivery_claim_succeeds(tmp_path):
    summary = tmp_path / "summary.json"
    registry = tmp_path / "registry.json"
    _summary(summary)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim_delivery(summary, registry), range(2)))

    assert sum(result["claimed"] for result in results) == 1


def test_degraded_and_complete_delivery_ids_can_both_send(tmp_path):
    registry = tmp_path / "registry.json"
    degraded = tmp_path / "degraded.json"
    complete = tmp_path / "complete.json"
    _summary(degraded, "run-1:degraded:aaa")
    _summary(complete, "run-1:complete:bbb")

    assert claim_delivery(degraded, registry)["claimed"]
    complete_delivery("run-1:degraded:aaa", "message-1", registry)
    assert claim_delivery(complete, registry)["claimed"]
    assert release_delivery("run-1:complete:bbb", registry)


def test_legacy_run_id_record_blocks_old_period_resend(tmp_path):
    registry = tmp_path / "registry.json"
    summary = tmp_path / "summary.json"
    _summary(summary)
    registry.write_text(json.dumps({"run-1": {"message_id": "old-message"}}), encoding="utf-8")

    result = claim_delivery(summary, registry)

    assert not result["claimed"]
    assert result["reason"] == "legacy run_id already sent"


def test_run_lock_rejects_second_holder(tmp_path):
    lock = tmp_path / "run.lock"

    with exclusive_lock(lock):
        with pytest.raises(LockUnavailable):
            with exclusive_lock(lock):
                pass
