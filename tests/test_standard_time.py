import struct
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from UK_news_scraper import standard_time as clock
from UK_news_scraper.run_summary import RunSummary, make_delivery_id


def stamp(value):
    ntp = value + clock.NTP_EPOCH
    return struct.pack("!II", int(ntp) % 2**32, int((ntp % 1) * 2**32))


def exchange(sent=1_700_000_000):
    request = bytearray(48)
    request[0] = 0x23
    request[40:] = stamp(sent)
    reply = bytearray(48)
    reply[0], reply[1] = 0x24, 2
    reply[24:32] = request[40:]
    reply[32:40], reply[40:48] = stamp(sent + 0.25), stamp(sent + 0.30)
    return request, reply


def test_ntp_offset_and_delay_include_server_processing_time():
    request, reply = exchange()
    offset, delay = clock.parse_reply(reply, request, 1_700_000_000, 1_700_000_000.1)
    assert offset == pytest.approx(0.225, abs=1e-6)
    assert delay == pytest.approx(0.05, abs=1e-6)


@pytest.mark.parametrize(("position", "value"), [(0, 0xE4), (0, 0x23), (0, 0x14), (1, 0), (1, 16), (24, 0)])
def test_unsynced_kiss_of_death_wrong_mode_version_or_origin_are_rejected(position, value):
    request, reply = exchange()
    reply[position] = value
    with pytest.raises(ValueError):
        clock.parse_reply(reply, request, 1_700_000_000, 1_700_000_000.1)


def test_short_zero_and_invalid_delay_packets_are_rejected():
    request, reply = exchange()
    with pytest.raises(ValueError, match="長度"):
        clock.parse_reply(reply[:47], request, 0, 1)
    reply[40:48] = bytes(8)
    with pytest.raises(ValueError, match="缺少"):
        clock.parse_reply(reply, request, 0, 1)
    request, reply = exchange()
    with pytest.raises(ValueError, match="延遲"):
        clock.parse_reply(reply, request, 1_700_000_000, 1_700_000_003)


def test_2036_ntp_era_rollover_is_unfolded_near_local_clock():
    reference = datetime(2040, 1, 1, tzinfo=UTC).timestamp()
    assert clock._decode(stamp(reference), reference) == reference


def test_success_selects_best_delay_and_anchors_to_monotonic_time(monkeypatch):
    monkeypatch.delenv("UK_NEWS_TIME_SYNC")
    monkeypatch.setattr(clock, "monotonic", lambda: 100.0)
    utc = datetime(2026, 10, 11, 16, tzinfo=UTC).timestamp()
    monkeypatch.setattr(
        clock, "query_server", lambda host: (utc, 100.0, -3600.0, 0.01 if host == clock.SERVERS[0] else 0.1)
    )
    result = clock.synchronize()
    assert result.source == "ntp" and result.server == clock.SERVERS[0]
    assert len(result.attempts) == 5
    assert clock.today_taipei().isoformat() == "2026-10-12"
    monkeypatch.setattr(clock, "time", lambda: 0.0)
    monkeypatch.setattr(clock, "monotonic", lambda: 105.0)
    assert clock.now_utc().timestamp() == utc + 5
    # OS jumps do not affect calibrated wall time and repeated runs reuse the sample.
    monkeypatch.setattr(clock, "query_server", lambda host: pytest.fail("unexpected second query"))
    assert clock.synchronize().source == "ntp"
    monkeypatch.setattr(clock, "monotonic", lambda: 2000.0)
    assert clock.status_payload()["source"] == "system"


def test_all_network_failures_fall_back_with_explicit_warning(monkeypatch):
    monkeypatch.delenv("UK_NEWS_TIME_SYNC")

    def fail(host):
        raise OSError("UDP blocked")

    monkeypatch.setattr(clock, "query_server", fail)
    state = clock.synchronize(force=True)
    assert state.source == "system"
    assert "UDP 123" in state.warning
    assert len(state.attempts) == 5
    assert abs(clock.now_utc().timestamp() - datetime.now(UTC).timestamp()) < 1


def test_slow_dns_workers_cannot_hold_the_caller_past_its_budget(monkeypatch):
    from threading import Event
    from time import monotonic

    monkeypatch.delenv("UK_NEWS_TIME_SYNC")
    release = Event()

    def slow(host):
        release.wait(1)
        raise OSError("DNS delayed")

    monkeypatch.setattr(clock, "query_server", slow)
    started = monotonic()
    try:
        assert clock.synchronize(force=True, timeout=0.02).source == "system"
        assert monotonic() - started < 0.3
    finally:
        release.set()


def test_sync_metadata_does_not_change_delivery_identity():
    summary = RunSummary(
        run_id="r",
        generated_at="now",
        period_start="2026-10-01",
        period_end="2026-10-12",
        output_file="report.xlsx",
        all_news_count=0,
        filtered_news_count=0,
        parliament_count=0,
        filtered_parliament_count=0,
        status="complete",
        warnings=(),
        data_fingerprint="f",
        delivery_id=make_delivery_id("r", "complete", "f"),
        source_health=(),
    )
    assert replace(summary, time_sync={"source": "ntp", "offset_seconds": 3600}).delivery_id == summary.delivery_id
