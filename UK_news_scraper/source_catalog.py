"""Versioned official-source inventory shared with the Rust desktop build."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json

from .models import Agency


GOVUK_LINKS = (
    "/government/news/",
    "/guidance/",
    "/government/publications/",
    "/government/consultations/",
    "/government/research/",
    "/government/statistics/",
)


@lru_cache(maxsize=1)
def catalog_entries() -> tuple[dict, ...]:
    path = files("UK_news_scraper").joinpath("data/source_catalog.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("不支援的官方來源目錄版本")
    return tuple(payload["sources"])


def searchable_agencies() -> tuple[Agency, ...]:
    return tuple(
        Agency(
            name_zh=entry["name_zh"] or entry["name_en"],
            name_en=entry["name_en"],
            short_name=entry["id"],
            homepage=entry["homepage"],
            feeds=(entry["feed"],) if entry.get("adapter") == "feed" else (f"{entry['homepage']}.atom",),
            link_include_patterns=GOVUK_LINKS if entry.get("adapter") == "govuk_search" else (),
        )
        for entry in catalog_entries()
        if entry["status"] == "searchable" and entry["adapter"] in {"govuk_search", "feed"}
    )
