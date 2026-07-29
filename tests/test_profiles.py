from dataclasses import replace
import json

import pytest

from UK_news_scraper.profiles import (
    FilterProfile,
    KeywordDefinition,
    KeywordStrength,
    ProfileTopic,
    default_profile,
    load_profiles,
    load_profiles_with_recovery,
    profile_from_dict,
    profile_hash,
    profile_to_dict,
    restore_default_profiles,
    save_profiles,
)


def _custom_profile() -> FilterProfile:
    return FilterProfile(
        profile_id="digital-health",
        name="數位健康",
        description="測試設定",
        version=1,
        selected_sources=("DSIT",),
        topics=(
            ProfileTopic(
                "數位健康",
                (
                    KeywordDefinition("digital health", KeywordStrength.CORE),
                    KeywordDefinition("health data", KeywordStrength.GENERAL),
                ),
            ),
        ),
        minimum_score=4,
    )


def test_profile_round_trip_and_hash_are_stable():
    profile = _custom_profile()

    restored = profile_from_dict(profile_to_dict(profile))

    assert restored == profile
    assert profile_hash(restored) == profile_hash(profile)


def test_profiles_are_saved_atomically_and_default_is_always_available(tmp_path):
    destination = tmp_path / "profiles.json"

    save_profiles([default_profile(), _custom_profile()], destination)
    loaded = load_profiles(destination)

    assert set(loaded) == {"uk-tech-law", "digital-health"}
    assert loaded["digital-health"].minimum_score == 4
    assert json.loads(destination.read_text(encoding="utf-8"))["schema_version"] == 1


def test_profile_rejects_duplicate_keywords():
    payload = profile_to_dict(_custom_profile())
    payload["topics"][0]["keywords"].append(
        {"phrase": "DIGITAL HEALTH", "strength": "supporting"}
    )

    with pytest.raises(ValueError, match="重複"):
        profile_from_dict(payload)


def test_legacy_profile_collection_is_migrated(tmp_path):
    destination = tmp_path / "profiles.json"
    legacy = profile_to_dict(_custom_profile())
    legacy.pop("version")
    legacy["topics"][0]["keywords"] = ["digital health"]
    destination.write_text(
        json.dumps({"profiles": [legacy]}, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_profiles(destination)

    keyword = loaded["digital-health"].topics[0].keywords[0]
    assert loaded["digital-health"].version == 1
    assert keyword.phrase == "digital health"
    assert keyword.strength is KeywordStrength.GENERAL


def test_corrupt_profile_file_is_quarantined_and_default_is_loaded(tmp_path):
    destination = tmp_path / "profiles.json"
    destination.write_text("{", encoding="utf-8")

    report = load_profiles_with_recovery(destination)

    assert set(report.profiles) == {"uk-tech-law"}
    assert report.recovery_path is not None
    assert report.recovery_path.exists()
    assert not destination.exists()
    assert "已載入內建設定" in report.warning


def test_invalid_collection_version_is_recovered(tmp_path):
    destination = tmp_path / "profiles.json"
    destination.write_text(
        json.dumps({"schema_version": None, "profiles": []}),
        encoding="utf-8",
    )

    report = load_profiles_with_recovery(destination)

    assert set(report.profiles) == {"uk-tech-law"}
    assert "版本必須是整數" in report.warning


def test_save_keeps_backup_and_restore_removes_custom_profiles(tmp_path):
    destination = tmp_path / "profiles.json"
    save_profiles([_custom_profile()], destination)
    save_profiles([replace(_custom_profile(), name="新版")], destination)

    backup = destination.with_suffix(".json.bak")
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["profiles"][0]["name"] == "數位健康"

    restored = restore_default_profiles(destination)

    assert set(restored) == {"uk-tech-law"}
    assert json.loads(destination.read_text(encoding="utf-8"))["profiles"] == []
