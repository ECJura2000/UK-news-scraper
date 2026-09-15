from __future__ import annotations

import json
from pathlib import Path

from UK_news_scraper.config import TOPIC_RULES
from UK_news_scraper.organisation_registry import (
    TEMPLATE_FILENAME,
    builtin_registry_dir,
    export_organisation_template,
    load_organisation_registry,
)


KNOWN_TOPICS = {rule.name for rule in TOPIC_RULES}


def _payload(canonical_id: str = "NEW") -> dict:
    return {
        "schema_version": 1,
        "module_version": "1.0.0",
        "canonical_id": canonical_id,
        "names": {
            "zh": "測試機關",
            "en": "Test Organisation",
            "short": canonical_id,
            "publisher_aliases": [],
        },
        "sources": {
            "homepage": "https://example.gov.uk/",
            "feeds": ["https://example.gov.uk/news.atom"],
            "news_pages": [],
            "official_pages": [],
            "adapter": "generic_rss",
            "fallbacks": [],
        },
        "filter": {
            "topics": ["AI"],
            "include_path_patterns": [],
            "exclude_title_patterns": [],
        },
        "health": {"critical": False, "minimum_items": 0, "maximum_age_days": 30},
        "history": {
            "effective_from": "2026-01-01",
            "predecessors": [],
            "successors": [],
            "transitional_sources": [],
        },
        "responsibility_by_topic": {},
    }


def _write(directory: Path, name: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_builtin_registry_has_fourteen_valid_modules():
    registry = load_organisation_registry(known_topics=KNOWN_TOPICS)
    assert len(registry.modules) == 14
    assert not registry.errors
    assert len(registry.registry_hash) == 64
    assert registry.module_ids == tuple(sorted(registry.module_ids, key=str.casefold))


def test_external_module_and_valid_override_take_effect(tmp_path):
    payload = _payload()
    _write(tmp_path, "new.json", payload)
    bist = json.loads((builtin_registry_dir() / "bist.json").read_text())
    bist["module_version"] = "external-test"
    _write(tmp_path, "override.json", bist)

    registry = load_organisation_registry(external_dir=tmp_path, known_topics=KNOWN_TOPICS)

    assert "NEW" in registry.module_ids
    active_bist = next(item for item in registry.modules if item.canonical_id == "BIST")
    assert active_bist.external
    assert active_bist.module_version == "external-test"


def test_invalid_reference_override_falls_back_and_invalid_new_module_is_skipped(tmp_path):
    bist = json.loads((builtin_registry_dir() / "bist.json").read_text())
    bist["history"]["successors"] = ["MISSING"]
    _write(tmp_path, "bist.json", bist)
    new = _payload()
    new["responsibility_by_topic"] = {"AI": "MISSING"}
    _write(tmp_path, "new.json", new)

    registry = load_organisation_registry(external_dir=tmp_path, known_topics=KNOWN_TOPICS)

    active_bist = next(item for item in registry.modules if item.canonical_id == "BIST")
    assert not active_bist.external
    assert "NEW" not in registry.module_ids
    assert len(registry.errors) == 2


def test_invalid_adapter_is_reported_without_replacing_builtin(tmp_path):
    bist = json.loads((builtin_registry_dir() / "bist.json").read_text())
    bist["sources"]["adapter"] = "python_plugin"
    _write(tmp_path, "bist.json", bist)

    registry = load_organisation_registry(external_dir=tmp_path, known_topics=KNOWN_TOPICS)

    assert not next(item for item in registry.modules if item.canonical_id == "BIST").external
    assert "未知 adapter" in registry.errors[0]


def test_template_exports_and_round_trips(tmp_path):
    target = export_organisation_template(tmp_path / TEMPLATE_FILENAME)
    payload = json.loads(target.read_text())
    external = tmp_path / "external"
    _write(external, "example.json", payload)
    registry = load_organisation_registry(external_dir=external, known_topics=KNOWN_TOPICS)
    assert "EXAMPLE" in registry.module_ids
