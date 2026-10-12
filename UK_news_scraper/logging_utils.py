from __future__ import annotations

import json
import os
from typing import Any

from .standard_time import now_utc


def log_event(level: str, event: str, message: str, **fields: Any) -> None:
    if os.environ.get("UK_NEWS_LOG_FORMAT", "").casefold() == "json":
        payload = {
            "timestamp": now_utc().isoformat(),
            "level": level,
            "event": event,
            "message": message,
            **fields,
        }
        print(json.dumps(payload, ensure_ascii=False, default=str))
        return
    print(f"[{level}] {message}")
