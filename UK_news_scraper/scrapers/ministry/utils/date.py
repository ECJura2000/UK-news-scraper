from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import struct_time


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_feed_datetime(entry: object) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, attr, None)
        if isinstance(value, struct_time):
            return datetime(*value[:6], tzinfo=UTC)

    for attr in ("published", "updated", "created", "dc_date"):
        value = getattr(entry, attr, None)
        if not value:
            continue
        try:
            return parse_datetime_text(str(value))
        except Exception:
            continue
    return None


def parse_datetime_text(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()

    try:
        return ensure_utc(parsedate_to_datetime(text))
    except Exception:
        pass

    normalized = text.replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(normalized))
    except Exception:
        pass

    for date_format in (
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
