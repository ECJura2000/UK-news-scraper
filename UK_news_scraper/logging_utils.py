from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any


def log_event(level: str, event: str, message: str, **fields: Any) -> None:
    if os.environ.get("UK_NEWS_LOG_FORMAT", "").casefold() == "json":
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "event": event,
            "message": message,
            **fields,
        }
        print(json.dumps(payload, ensure_ascii=False, default=str))
        return
    print(f"[{level}] {message}")
