import json

import pytest

from UK_news_scraper.profiles import (
    FilterProfile,
    KeywordDefinition,
    KeywordStrength,
    ProfileTopic,
    default_profile,
    load_profiles,
    profile_from_dict,
    profile_hash,
    profile_to_dict,
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
