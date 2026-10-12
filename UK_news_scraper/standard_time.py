"""Bounded SNTP calibration for application wall time; never sets the OS clock."""

from __future__ import annotations

import json
import os
import queue
import socket
import struct
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from threading import Lock, Thread
from time import monotonic, time
from typing import Any
from zoneinfo import ZoneInfo

SERVERS = tuple(f"{name}.stdtime.gov.tw" for name in ("tock", "watch", "time", "clock", "tick"))
NTP_EPOCH = 2_208_988_800
ERA_SECONDS = 2**32
MAX_AGE_SECONDS = 1800


@dataclass
class TimeSync:
    source: str = "system"
    server: str = ""
    checked_at: str = ""
    offset_seconds: float | None = None
    round_trip_seconds: float | None = None
    warning: str = "尚未連接國家標準時間，使用本機時間"
    attempts: list[dict[str, str]] = field(default_factory=list)


_lock = Lock()
_status = TimeSync()
_anchor: tuple[float, float] | None = None
_last_attempt = -float("inf")


def _decode(raw: bytes, reference: float) -> float:
    seconds, fraction = struct.unpack("!II", raw)
    base = seconds - NTP_EPOCH + fraction / ERA_SECONDS
    return float(base + round((reference - base) / ERA_SECONDS) * ERA_SECONDS)


def parse_reply(packet: bytes, request: bytes, sent: float, received: float) -> tuple[float, float]:
    if len(packet) < 48 or len(request) != 48:
        raise ValueError("NTP 封包長度錯誤")
    if packet[0] >> 6 == 3 or (packet[0] >> 3) & 7 not in (3, 4) or packet[0] & 7 != 4:
        raise ValueError("NTP 伺服器未同步或回應模式錯誤")
    if not 1 <= packet[1] <= 15:
        raise ValueError("NTP 伺服器拒絕查詢或 stratum 無效")
    if packet[24:32] != request[40:48]:
        raise ValueError("NTP 回應不屬於本次查詢")
    if not any(packet[32:40]) or not any(packet[40:48]):
        raise ValueError("NTP 回應缺少伺服器時間")
    t2, t3 = _decode(packet[32:40], received), _decode(packet[40:48], received)
    delay = (received - sent) - (t3 - t2)
    if t3 < t2 or not -0.002 <= delay <= 2:
        raise ValueError("NTP 網路延遲或伺服器時間無效")
    return ((t2 - sent) + (t3 - received)) / 2, max(0.0, delay)


def query_server(server: str, timeout: float = 0.8) -> tuple[float, float, float, float]:
    addresses = socket.getaddrinfo(server, 123, type=socket.SOCK_DGRAM)
    family, kind, proto, _, address = addresses[0]
    with socket.socket(family, kind, proto) as client:
        client.settimeout(timeout)
        client.connect(address)
        request = bytearray(48)
        request[0] = 0x23
        wall = time()
        seconds, fraction = divmod(wall + NTP_EPOCH, 1)
        request[40:48] = struct.pack("!II", int(seconds) % ERA_SECONDS, int(fraction * ERA_SECONDS))
        request[46:48] = os.urandom(2)
        sent = _decode(bytes(request[40:48]), wall)
        started = monotonic()
        client.send(request)
        packet = client.recv(512)
        arrived = monotonic()
        received = sent + arrived - started
        offset, delay = parse_reply(packet, bytes(request), sent, received)
        return received + offset, arrived, offset, delay


def synchronize(*, force: bool = False, timeout: float = 2.0) -> TimeSync:
    global _status, _anchor, _last_attempt
    with _lock:
        elapsed = monotonic() - _last_attempt
        if not force and elapsed < (MAX_AGE_SECONDS if _anchor else 60):
            return _status
        _last_attempt = monotonic()
        if os.environ.get("UK_NEWS_TIME_SYNC", "").lower() == "off":
            _anchor = None
            _status = TimeSync(checked_at=datetime.now(UTC).isoformat(), warning="NTP 校時已停用，使用本機時間")
            return _status
        answers: queue.Queue[tuple[str, tuple[float, float, float, float] | None, str]] = queue.Queue()

        def fetch(server: str) -> None:
            try:
                answers.put((server, query_server(server), ""))
            except (OSError, ValueError, IndexError) as exc:
                answers.put((server, None, str(exc)))

        for server in SERVERS:
            Thread(target=fetch, args=(server,), daemon=True).start()
        deadline = monotonic() + timeout
        samples: list[tuple[str, tuple[float, float, float, float]]] = []
        attempts: list[dict[str, str]] = []
        while len(attempts) < len(SERVERS):
            try:
                server, sample, error = answers.get(timeout=max(0, deadline - monotonic()))
            except queue.Empty:
                break
            attempts.append({"server": server, "result": "ok" if sample else error})
            if sample:
                samples.append((server, sample))
        answered = {attempt["server"] for attempt in attempts}
        attempts.extend(
            {"server": server, "result": "查詢期限內未收到有效回應"} for server in SERVERS if server not in answered
        )
        if samples:
            server, (utc, anchor, offset, delay) = min(samples, key=lambda value: value[1][3])
            _anchor = (utc, anchor)
            _status = TimeSync("ntp", server, datetime.fromtimestamp(utc, UTC).isoformat(), offset, delay, "", attempts)
        else:
            _anchor = None
            _status = TimeSync(
                checked_at=datetime.now(UTC).isoformat(),
                warning="國家標準時間 NTP 校時失敗，使用本機時間；請檢查 DNS 與 UDP 123 連線",
                attempts=attempts,
            )
        return _status


def now_utc() -> datetime:
    anchor = _anchor
    if anchor and monotonic() - anchor[1] <= MAX_AGE_SECONDS:
        return datetime.fromtimestamp(anchor[0] + monotonic() - anchor[1], UTC)
    return datetime.now(UTC)


def today_taipei() -> date:
    return now_utc().astimezone(ZoneInfo("Asia/Taipei")).date()


def status_payload() -> dict[str, Any]:
    result = asdict(_status)
    if _anchor and monotonic() - _anchor[1] > MAX_AGE_SECONDS:
        result.update(source="system", warning="NTP 校時已超過 30 分鐘，使用本機時間")
    result["utc"] = now_utc().isoformat()
    return result


if __name__ == "__main__":
    synchronize(force=True)
    print(json.dumps(status_payload(), ensure_ascii=False, indent=2))
