from __future__ import annotations

from datetime import datetime, timezone
import json
import os


def log_event(level: str, event: str, message: str, **fields) -> None:
    if os.environ.get("UK_NEWS_LOG_FORMAT", "").casefold() == "json":
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            "message": message,
            **fields,
        }
        print(json.dumps(payload, ensure_ascii=False, default=str))
        return
    print(f"[{level}] {message}")
