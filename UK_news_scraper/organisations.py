from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
from urllib.parse import urlparse

from .models import NewsItem, SourceHealth
from .config import AGENCIES, ORGANISATION_REGISTRY
from .http.async_client import get_text


@dataclass(frozen=True)
class OrganisationRecord:
    canonical_id: str
    official_name: str
    govuk_slug: str
    effective_from: str
    predecessors: tuple[str, ...] = ()
    successors: tuple[str, ...] = ()
    transitional_feeds: tuple[str, ...] = ()

# Compatibility views backed by the active JSON registry.
ORGANISATION_REGISTRY_VERSION = ORGANISATION_REGISTRY.registry_hash
ORGANISATIONS = tuple(
    OrganisationRecord(
        module.canonical_id,
        str(module.names["en"]),
        urlparse(str(module.sources["homepage"])).path.rsplit("/", 1)[-1],
        str(module.history["effective_from"]),
        predecessors=tuple(module.history["predecessors"]),
        successors=tuple(module.history["successors"]),
        transitional_feeds=tuple(module.sources["feeds"])
        if module.history["transitional_sources"]
        else (),
    )
    for module in ORGANISATION_REGISTRY.modules
)
TRANSITIONAL_SOURCES = tuple(
    f"{module.canonical_id}:{source}"
    for module in ORGANISATION_REGISTRY.modules
    for source in module.history["transitional_sources"]
)


def apply_organisation_metadata(items: list[NewsItem]) -> None:
    modules = {module.canonical_id: module for module in ORGANISATION_REGISTRY.modules}
    for item in items:
        item.publisher_organisation = item.publisher_organisation or item.agency_en or item.agency
        module = modules.get(item.unit_category or "")
        if module and module.responsibility_by_topic:
            owners = {
                module.responsibility_by_topic[topic]
                for topic in item.matched_topics
                if topic in module.responsibility_by_topic
            }
            owner_order = [*module.history["successors"], *ORGANISATION_REGISTRY.module_ids]
            item.responsibility_owner = " / ".join(
                owner
                for owner in dict.fromkeys(owner_order)
                if owner in owners
            )
        else:
            item.responsibility_owner = item.responsibility_owner or item.agency


def audit_content_api_publishers(items: list[NewsItem]) -> tuple[str, ...]:
    candidates = {
        item.link: item
        for item in items
        if urlparse(item.link).netloc.casefold().endswith("gov.uk")
        and urlparse(item.source_feed).netloc.casefold().endswith("gov.uk")
    }
    if not candidates:
        return ()
    changes: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(_content_api_publisher, candidates.items())
        for (link, item), (publisher, error) in zip(candidates.items(), results, strict=True):
            if error:
                changes.append(f"content_api_unavailable:{link}")
                continue
            if not publisher:
                changes.append(f"content_api_organisation_missing:{link}")
                continue
            item.publisher_organisation = publisher
    return tuple(sorted(changes))


def _content_api_publisher(item: tuple[str, NewsItem]) -> tuple[str, str]:
    link, _ = item
    path = urlparse(link).path
    try:
        payload = json.loads(get_text(f"https://www.gov.uk/api/content{path}"))
        organisations = payload.get("links", {}).get("organisations", [])
        title = next(
            (str(value.get("title", "")).strip() for value in organisations if value.get("title")),
            "",
        )
        return title, ""
    except Exception as exc:
        return "", str(exc)


def audit_organisation_state(
    items: list[NewsItem],
    source_health: tuple[SourceHealth, ...],
) -> tuple[str, tuple[str, ...]]:
    known_publishers = {record.official_name for record in ORGANISATIONS}
    known_publishers.update(agency.name_en for agency in AGENCIES)
    known_publishers.update(
        str(alias)
        for module in ORGANISATION_REGISTRY.modules
        for alias in module.names["publisher_aliases"]
    )
    changes = sorted(
        {
            f"unknown_publisher:{item.publisher_organisation}"
            for item in items
            if item.publisher_organisation and item.publisher_organisation not in known_publishers
        }
    )
    transitional_ids = {
        module.canonical_id
        for module in ORGANISATION_REGISTRY.modules
        if module.history["transitional_sources"]
    }
    for health in source_health:
        if health.source in transitional_ids and not health.success:
            changes.append(f"transitional_source_unavailable:{health.source}")
    return ("degraded" if changes else "ok", tuple(changes))
