from datetime import datetime, timezone

from UK_news_scraper.models import NewsItem
from UK_news_scraper.profiles import (
    FilterProfile,
    KeywordDefinition,
    KeywordStrength,
    ProfileTopic,
)
from UK_news_scraper.relevance import assess_relevance
from UK_news_scraper.scrapers.ministry.registry import apply_topic_filter


def _item(title: str, summary: str = "", link: str = "https://example.com") -> NewsItem:
    return NewsItem("Agency", "Agency", "A", title, link, datetime.now(timezone.utc), summary)


def test_broad_keyword_alone_is_not_relevant():
    assert apply_topic_filter([_item("Technology award announced")]) == []


def test_specific_title_keyword_is_relevant_and_explainable():
    item = _item("New rules for artificial intelligence")
    assert apply_topic_filter([item]) == [item]
    assert item.relevance_score >= 3
    assert item.relevance_level
    assert item.title_matched_keywords == ["artificial intelligence"]


def test_multiple_broad_signals_can_reach_threshold():
    item = _item("Technology platform launched")
    assert apply_topic_filter([item]) == [item]
    assert set(item.title_matched_keywords) == {"platform", "technology"}


def test_consolidated_policy_keywords_are_weighted_and_explainable():
    items = [
        _item(
            "AI Security Institute publishes evaluation update",
            "Frontier AI and AI and data protection.",
            "https://example.com/ai",
        ),
        _item(
            "Open Government Data Framework refreshed",
            "Updated data reuse policy and One Login guidance.",
            "https://example.com/data",
        ),
        _item(
            "Cyber Essentials guidance for supply chains",
            "SBOM and critical infrastructure protection.",
            "https://example.com/cyber",
        ),
    ]

    filtered = apply_topic_filter(items)

    assert len(filtered) == 3
    assert all(item.relevance_score >= 3 for item in filtered)
    assert any("AI" in item.matched_topics for item in filtered)
    assert any("資料治理/隱私/數位身份" in item.matched_topics for item in filtered)
    assert any("網路安全/資安" in item.matched_topics for item in filtered)


def test_custom_profile_uses_three_strength_levels_and_configured_threshold():
    profile = FilterProfile(
        profile_id="custom-policy",
        name="Custom policy",
        description="",
        version=1,
        selected_sources=("BIST",),
        topics=(
            ProfileTopic(
                "Policy",
                (
                    KeywordDefinition("alpha framework", KeywordStrength.CORE),
                    KeywordDefinition("beta rule", KeywordStrength.GENERAL),
                    KeywordDefinition("technology", KeywordStrength.SUPPORTING),
                ),
            ),
        ),
        minimum_score=10,
    )

    assessment = assess_relevance(
        "Alpha framework and technology",
        "The beta rule applies.",
        profile,
    )

    assert assessment.score == 12
    assert assessment.included is True
    assert assessment.core_keywords == ("alpha framework",)
    assert assessment.general_keywords == ("beta rule",)
    assert assessment.supporting_keywords == ("technology",)


def test_supporting_keyword_alone_can_be_excluded_by_threshold():
    profile = FilterProfile(
        profile_id="support-test",
        name="Support test",
        description="",
        version=1,
        selected_sources=("BIST",),
        topics=(
            ProfileTopic(
                "Policy",
                (KeywordDefinition("technology", KeywordStrength.SUPPORTING),),
            ),
        ),
        minimum_score=3,
    )

    assert assess_relevance("Technology update", "", profile).included is False
