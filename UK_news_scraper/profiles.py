from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from .config import AGENCIES, TOPIC_RULES


PROFILE_SCHEMA_VERSION = 1
DEFAULT_PROFILE_ID = "uk-tech-law"
PARLIAMENT_SOURCE_ID = "UK Parliament"


class KeywordStrength(str, Enum):
    CORE = "core"
    GENERAL = "general"
    SUPPORTING = "supporting"

    @property
    def label(self) -> str:
        return {
            self.CORE: "核心",
            self.GENERAL: "一般",
            self.SUPPORTING: "輔助",
        }[self]


@dataclass(frozen=True)
class KeywordDefinition:
    phrase: str
    strength: KeywordStrength = KeywordStrength.GENERAL


@dataclass(frozen=True)
class ProfileTopic:
    name: str
    keywords: tuple[KeywordDefinition, ...]


@dataclass(frozen=True)
class FilterProfile:
    profile_id: str
    name: str
    description: str
    version: int
    selected_sources: tuple[str, ...]
    topics: tuple[ProfileTopic, ...]
    minimum_score: int = 3

    @property
    def is_default(self) -> bool:
        return self.profile_id == DEFAULT_PROFILE_ID


_SUPPORTING_KEYWORDS = {
    "copyright",
    "evaluation",
    "innovation",
    "platform",
    "resilience",
    "supply chain",
    "technology",
}


def default_profile() -> FilterProfile:
    topics = tuple(
        ProfileTopic(
            name=rule.name,
            keywords=tuple(
                KeywordDefinition(keyword, _default_strength(keyword))
                for keyword in rule.keywords
            ),
        )
        for rule in TOPIC_RULES
    )
    sources = tuple(agency.short_name for agency in AGENCIES) + (PARLIAMENT_SOURCE_ID,)
    return FilterProfile(
        profile_id=DEFAULT_PROFILE_ID,
        name="UK 科技法制",
        description="英國科技、AI、資料治理、平台、資安、半導體與量子政策觀測",
        version=PROFILE_SCHEMA_VERSION,
        selected_sources=sources,
        topics=topics,
        minimum_score=3,
    )


def validate_profile(profile: FilterProfile) -> FilterProfile:
    if profile.version != PROFILE_SCHEMA_VERSION:
        raise ValueError(f"不支援的設定檔版本：{profile.version}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}", profile.profile_id):
        raise ValueError("設定檔 ID 只能使用小寫英數與連字號，長度 2 至 49 字元")
    if not profile.name.strip():
        raise ValueError("設定檔名稱不可空白")
    if profile.minimum_score < 1:
        raise ValueError("最低分數必須大於等於 1")
    if not profile.selected_sources:
        raise ValueError("至少選擇一個資料來源")
    available_sources = {agency.short_name for agency in AGENCIES} | {PARLIAMENT_SOURCE_ID}
    unknown_sources = set(profile.selected_sources) - available_sources
    if unknown_sources:
        raise ValueError(f"設定檔包含未知來源：{sorted(unknown_sources)}")
    if not profile.topics:
        raise ValueError("至少建立一個主題")

    seen_phrases: set[str] = set()
    for topic in profile.topics:
        if not topic.name.strip():
            raise ValueError("主題名稱不可空白")
        if not topic.keywords:
            raise ValueError(f"主題「{topic.name}」至少需要一個關鍵詞")
        for keyword in topic.keywords:
            phrase = keyword.phrase.strip()
            if not phrase:
                raise ValueError(f"主題「{topic.name}」包含空白關鍵詞")
            normalized = phrase.casefold()
            if normalized in seen_phrases:
                raise ValueError(f"關鍵詞重複：{phrase}")
            seen_phrases.add(normalized)
    return profile


def profile_hash(profile: FilterProfile) -> str:
    payload = json.dumps(
        profile_to_dict(profile),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def profile_to_dict(profile: FilterProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "description": profile.description,
        "version": profile.version,
        "selected_sources": list(profile.selected_sources),
        "topics": [
            {
                "name": topic.name,
                "keywords": [
                    {
                        "phrase": keyword.phrase,
                        "strength": keyword.strength.value,
                    }
                    for keyword in topic.keywords
                ],
            }
            for topic in profile.topics
        ],
        "minimum_score": profile.minimum_score,
    }


def profile_from_dict(payload: object) -> FilterProfile:
    if not isinstance(payload, dict):
        raise ValueError("設定檔必須是 JSON object")
    try:
        topics = tuple(
            ProfileTopic(
                name=str(topic["name"]),
                keywords=tuple(
                    KeywordDefinition(
                        phrase=str(keyword["phrase"]),
                        strength=KeywordStrength(keyword.get("strength", KeywordStrength.GENERAL.value)),
                    )
                    for keyword in topic["keywords"]
                ),
            )
            for topic in payload["topics"]
        )
        profile = FilterProfile(
            profile_id=str(payload["profile_id"]),
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            version=int(payload.get("version", PROFILE_SCHEMA_VERSION)),
            selected_sources=tuple(str(source) for source in payload["selected_sources"]),
            topics=topics,
            minimum_score=int(payload.get("minimum_score", 3)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"設定檔格式錯誤：{exc}") from exc
    return validate_profile(profile)


def profiles_path() -> Path:
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "UKNewsScraper" / "profiles.json"


def load_profiles(path: str | Path | None = None) -> dict[str, FilterProfile]:
    destination = Path(path) if path else profiles_path()
    profiles = {DEFAULT_PROFILE_ID: default_profile()}
    if not destination.exists():
        return profiles
    try:
        payload = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"無法讀取設定檔：{exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
        raise ValueError("設定檔集合必須包含 profiles array")
    for item in payload["profiles"]:
        profile = profile_from_dict(item)
        profiles[profile.profile_id] = profile
    return profiles


def save_profiles(profiles: list[FilterProfile], path: str | Path | None = None) -> Path:
    destination = Path(path) if path else profiles_path()
    validated = [validate_profile(profile) for profile in profiles if not profile.is_default]
    ids = [profile.profile_id for profile in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("設定檔 ID 不可重複")
    payload = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profiles": [profile_to_dict(profile) for profile in validated],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_profile(reference: str | Path | None) -> FilterProfile:
    if reference is None:
        return default_profile()
    path = Path(reference).expanduser()
    if path.exists():
        return profile_from_dict(json.loads(path.read_text(encoding="utf-8")))
    profiles = load_profiles()
    try:
        return profiles[str(reference)]
    except KeyError as exc:
        raise ValueError(f"找不到設定檔：{reference}") from exc


def safe_profile_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.casefold()).strip("-")
    return normalized or "custom"


def _default_strength(keyword: str) -> KeywordStrength:
    normalized = keyword.casefold()
    if normalized in _SUPPORTING_KEYWORDS:
        return KeywordStrength.SUPPORTING
    if " " in keyword.strip() or len(keyword.strip()) >= 10:
        return KeywordStrength.CORE
    return KeywordStrength.GENERAL
