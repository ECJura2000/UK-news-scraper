from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any
from urllib.parse import urlparse

from .models import Agency


REGISTRY_SCHEMA_VERSION = 1
SUPPORTED_ADAPTERS = frozenset(
    {"govuk_atom", "generic_rss", "html_index", "electoral_sitemap"}
)
SUPPORTED_FALLBACKS = frozenset({"google_news"})
TEMPLATE_FILENAME = "organisation.example.json"


@dataclass(frozen=True)
class OrganisationModule:
    canonical_id: str
    module_version: str
    names: dict[str, Any]
    sources: dict[str, Any]
    filter: dict[str, Any]
    health: dict[str, Any]
    history: dict[str, Any]
    responsibility_by_topic: dict[str, str]
    payload: dict[str, Any]
    source_path: str
    external: bool = False

    def to_agency(self) -> Agency:
        return Agency(
            name_zh=str(self.names["zh"]),
            name_en=str(self.names["en"]),
            short_name=str(self.names["short"]),
            homepage=str(self.sources["homepage"]),
            feeds=tuple(self.sources["feeds"]),
            news_pages=tuple(self.sources["news_pages"]),
            topics=tuple(self.filter["topics"]),
            link_include_patterns=tuple(self.filter["include_path_patterns"]),
            official_pages=tuple(self.sources["official_pages"]),
            scraper_adapter=str(self.sources["adapter"]),
            fallbacks=tuple(self.sources["fallbacks"]),
            exclude_title_patterns=tuple(self.filter["exclude_title_patterns"]),
        )


@dataclass(frozen=True)
class OrganisationRegistry:
    modules: tuple[OrganisationModule, ...]
    errors: tuple[str, ...]
    registry_hash: str

    @property
    def agencies(self) -> tuple[Agency, ...]:
        return tuple(module.to_agency() for module in self.modules)

    @property
    def module_ids(self) -> tuple[str, ...]:
        return tuple(module.canonical_id for module in self.modules)

    @property
    def minimum_items(self) -> dict[str, int]:
        return {
            module.canonical_id: int(module.health["minimum_items"])
            for module in self.modules
            if int(module.health["minimum_items"]) > 0
        }

    @property
    def maximum_age_days(self) -> dict[str, int]:
        return {
            module.canonical_id: int(module.health["maximum_age_days"])
            for module in self.modules
        }

    @property
    def topics_by_source(self) -> dict[str, frozenset[str]]:
        return {
            module.canonical_id: frozenset(str(topic) for topic in module.filter["topics"])
            for module in self.modules
        }

    @property
    def module_summaries(self) -> tuple[dict[str, str | bool], ...]:
        return tuple(
            {
                "canonical_id": module.canonical_id,
                "module_version": module.module_version,
                "source": module.source_path,
                "external": module.external,
            }
            for module in self.modules
        )


def builtin_registry_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "organisation_registry"
    return Path(__file__).resolve().parent.parent / "organisation_registry"


def external_registry_dir() -> Path:
    if configured := os.environ.get("UK_NEWS_ORGANISATION_DIR"):
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "UKNewsScraper" / "organisations.d"


def load_organisation_registry(
    *,
    builtin_dir: Path | None = None,
    external_dir: Path | None = None,
    known_topics: set[str] | None = None,
) -> OrganisationRegistry:
    builtin_dir = builtin_dir or builtin_registry_dir()
    external_dir = external_dir or external_registry_dir()
    builtins, builtin_errors = _load_directory(builtin_dir, external=False, known_topics=known_topics)
    if builtin_errors:
        raise ValueError("內建機關 registry 無效：" + "；".join(builtin_errors))
    builtin_by_id = {module.canonical_id: module for module in builtins}
    active = dict(builtin_by_id)
    external_modules, external_errors = _load_directory(
        external_dir,
        external=True,
        known_topics=known_topics,
    )
    for module in external_modules:
        active[module.canonical_id] = module
    modules = tuple(active[key] for key in sorted(active, key=str.casefold))
    reference_errors = _validate_references(modules)
    bad_paths = {
        error.split(":未知機關引用：", 1)[0]
        for error in reference_errors
    }
    if bad_paths:
        recovered: dict[str, OrganisationModule] = {}
        for module in modules:
            if module.source_path not in bad_paths:
                recovered[module.canonical_id] = module
            elif module.external and module.canonical_id in builtin_by_id:
                recovered[module.canonical_id] = builtin_by_id[module.canonical_id]
        modules = tuple(recovered[key] for key in sorted(recovered, key=str.casefold))
        reference_errors.extend(_validate_references(modules))
    errors = tuple(sorted({*external_errors, *reference_errors}))
    return OrganisationRegistry(modules, errors, _registry_hash(modules))


def export_organisation_template(destination: str | Path) -> Path:
    source = builtin_registry_dir() / TEMPLATE_FILENAME
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def _load_directory(
    directory: Path,
    *,
    external: bool,
    known_topics: set[str] | None,
) -> tuple[list[OrganisationModule], list[str]]:
    if not directory.exists():
        return [], []
    modules: list[OrganisationModule] = []
    errors: list[str] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json"), key=lambda value: value.name.casefold()):
        if path.name == TEMPLATE_FILENAME:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            module = _parse_module(payload, path, external=external, known_topics=known_topics)
            if module.canonical_id in seen:
                raise ValueError(f"canonical_id 重複：{module.canonical_id}")
            seen.add(module.canonical_id)
            modules.append(module)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"{path}:{exc}")
    return modules, errors


def _parse_module(
    payload: object,
    path: Path,
    *,
    external: bool,
    known_topics: set[str] | None,
) -> OrganisationModule:
    if not isinstance(payload, dict):
        raise ValueError("根節點必須是 object")
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(f"不支援的 schema_version：{payload.get('schema_version')}")
    required = {
        "module_version", "canonical_id", "names", "sources", "filter", "health",
        "history", "responsibility_by_topic",
    }
    if missing := required - payload.keys():
        raise ValueError(f"缺少欄位：{sorted(missing)}")
    canonical_id = str(payload["canonical_id"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}", canonical_id):
        raise ValueError("canonical_id 格式錯誤")
    names = _object(payload["names"], "names")
    sources = _object(payload["sources"], "sources")
    filters = _object(payload["filter"], "filter")
    health = _object(payload["health"], "health")
    history = _object(payload["history"], "history")
    responsibility = _object(payload["responsibility_by_topic"], "responsibility_by_topic")
    _require_keys(names, {"zh", "en", "short", "publisher_aliases"}, "names")
    _require_keys(sources, {"homepage", "feeds", "news_pages", "official_pages", "adapter", "fallbacks"}, "sources")
    _require_keys(filters, {"topics", "include_path_patterns", "exclude_title_patterns"}, "filter")
    _require_keys(health, {"critical", "minimum_items", "maximum_age_days"}, "health")
    _require_keys(history, {"effective_from", "predecessors", "successors", "transitional_sources"}, "history")
    if any(not str(names[key]).strip() for key in ("zh", "en", "short")):
        raise ValueError("機關名稱不可空白")
    adapter = str(sources["adapter"])
    if adapter not in SUPPORTED_ADAPTERS:
        raise ValueError(f"未知 adapter：{adapter}")
    if unknown := set(map(str, sources["fallbacks"])) - SUPPORTED_FALLBACKS:
        raise ValueError(f"未知 fallback：{sorted(unknown)}")
    urls = [sources["homepage"], *sources["feeds"], *sources["news_pages"], *sources["official_pages"]]
    if any(urlparse(str(url)).scheme != "https" for url in urls):
        raise ValueError("所有來源 URL 必須使用 https")
    topics = list(map(str, filters["topics"]))
    if not topics:
        raise ValueError("filter.topics 不可空白")
    if known_topics is not None and (unknown := set(topics) - known_topics):
        raise ValueError(f"未知主題：{sorted(unknown)}")
    if not isinstance(health["critical"], bool):
        raise ValueError("health.critical 必須是 boolean")
    if int(health["minimum_items"]) < 0 or int(health["maximum_age_days"]) < 1:
        raise ValueError("health 門檻不在允許範圍")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(history["effective_from"])):
        raise ValueError("history.effective_from 必須是 YYYY-MM-DD")
    normalized = json.loads(json.dumps(payload, ensure_ascii=False))
    return OrganisationModule(
        canonical_id=canonical_id,
        module_version=str(payload["module_version"]),
        names=names,
        sources=sources,
        filter=filters,
        health=health,
        history=history,
        responsibility_by_topic={str(key): str(value) for key, value in responsibility.items()},
        payload=normalized,
        source_path=str(path),
        external=external,
    )


def _validate_references(modules: tuple[OrganisationModule, ...]) -> list[str]:
    ids = {module.canonical_id for module in modules}
    errors: list[str] = []
    for module in modules:
        references = [*module.history["successors"], *module.responsibility_by_topic.values()]
        if unknown := set(map(str, references)) - ids:
            errors.append(f"{module.source_path}:未知機關引用：{sorted(unknown)}")
    return errors


def _registry_hash(modules: tuple[OrganisationModule, ...]) -> str:
    payload = [module.payload for module in modules]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必須是 object")
    return value


def _require_keys(value: dict[str, Any], keys: set[str], name: str) -> None:
    if missing := keys - value.keys():
        raise ValueError(f"{name} 缺少欄位：{sorted(missing)}")
