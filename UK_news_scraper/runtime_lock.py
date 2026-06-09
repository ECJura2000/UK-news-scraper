from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time


class LockUnavailable(RuntimeError):
    pass


@contextmanager
def exclusive_lock(
    path: str | Path,
    stale_after_seconds: int = 6 * 60 * 60,
    wait_seconds: float = 0,
):
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        _remove_stale_lock(lock_path, stale_after_seconds)
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise LockUnavailable(f"已有執行中的工作持有鎖定：{lock_path}") from exc
            time.sleep(0.02)

    payload = {
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _remove_stale_lock(path: Path, stale_after_seconds: int) -> None:
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return
    if age > stale_after_seconds:
        path.unlink(missing_ok=True)
