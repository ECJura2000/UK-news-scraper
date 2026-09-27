"""Additive audit metadata; never included in fingerprint v3 or delivery identity."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from .models import NewsItem, ParliamentBriefing, SourceHealth


PARSER_VERSION = "v1"


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return value.strip()
    host = (parts.hostname or "").lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, "", ""))


def record_provenance(
    news: list[NewsItem],
    parliament: list[ParliamentBriefing],
    fetched_at: str,
    source_health: tuple[SourceHealth, ...] = (),
) -> tuple[dict[str, str], ...]:
    observed_at = {source.source: source.fetched_at for source in source_health if source.fetched_at}
    records = [
        {
            "record_type": "news",
            "source_id": item.unit_category or item.agency,
            "url": item.link,
            "canonical_url": canonical_url(item.link),
            "source_feed": item.source_feed,
            "fetched_at": observed_at.get(item.unit_category or item.agency, fetched_at),
            "parser_version": PARSER_VERSION,
        }
        for item in news
    ]
    records.extend(
        {
            "record_type": "parliament",
            "source_id": item.publisher,
            "url": item.webpage_url,
            "canonical_url": canonical_url(item.webpage_url),
            "source_feed": item.fetched_from,
            "fetched_at": observed_at.get(f"{item.publisher} RSS", fetched_at),
            "parser_version": PARSER_VERSION,
        }
        for item in parliament
    )
    return tuple(sorted(records, key=lambda record: (record["record_type"], record["source_id"], record["canonical_url"])))
