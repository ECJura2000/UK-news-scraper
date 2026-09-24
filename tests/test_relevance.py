from datetime import datetime, timezone
import pytest

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


@pytest.mark.parametrize(
    ("title", "summary", "expected_topic"),
    [
        ("Shaping Tomorrow: The UK's Digital Standards Strategy 2026 to 2030", "", "數位治理/標準/公共部門"),
        ("Final storage and access technologies guidance published", "", "資料治理/隱私/數位身份"),
        ("Company Guidance | Secure Innovation", "", "網路安全/資安"),
        ("Government procurement to prioritise national security", "", "數位治理/標準/公共部門"),
        ("A new framework was published", "Public sector AI procurement rules and risk management.", "數位治理/標準/公共部門"),
        ("AI Hardware Plan", "", "AI"),
        ("App stores agree to fairer terms", "", "數位平台"),
    ],
)
def test_curated_policy_cases_are_recalled(title, summary, expected_topic):
    assessment = assess_relevance(title, summary)
    assert assessment.included
    assert expected_topic in assessment.topics
    assert assessment.keywords


@pytest.mark.parametrize(
    "title",
    [
        "Technology award announced",
        "Procurement team appointment announced",
        "Cat Little Appointed as New Permanent Secretary, Department for Business, Innovation, Science and Trade",
        "Cookie recipe competition opens",
        "Transparency data: IPO government procurement card spending 2026",
    ],
)
def test_broad_or_administrative_titles_are_not_enough(title):
    assert not assess_relevance(title, "").included


def test_organisation_homepage_is_not_an_initial_selection():
    item = _item("Department for Business, Innovation, Science and Trade", "Science and technology policy")
    item.link = "https://www.gov.uk/government/organisations/department-for-business-innovation-science-and-trade"
    assert apply_topic_filter([item]) == []


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


def test_supporting_keyword_repeated_in_title_and_summary_counts_once():
    profile = FilterProfile(
        profile_id="support-repeat-test",
        name="Support repeat test",
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

    assessment = assess_relevance(
        "Technology update",
        "Technology programme details.",
        profile,
    )

    assert assessment.score == 2
    assert assessment.included is False


def test_overlapping_keywords_keep_the_longest_phrase():
    item = _item("GOV.UK One Login roadmap published")

    filtered = apply_topic_filter([item])

    assert filtered == [item]
    assert item.title_matched_keywords == ["GOV.UK One Login"]
    assert "One Login" not in item.matched_keywords


def test_summary_boilerplate_is_removed_before_scoring():
    profile = FilterProfile(
        profile_id="boilerplate-test",
        name="Boilerplate test",
        description="",
        version=1,
        selected_sources=("BIST",),
        topics=(
            ProfileTopic(
                "Policy",
                (KeywordDefinition("technology", KeywordStrength.GENERAL),),
            ),
        ),
        minimum_score=3,
    )

    assessment = assess_relevance(
        "Annual report published",
        "The Department for Business and Trade is responsible for technology policy.",
        profile,
    )

    assert assessment.score == 0
    assert assessment.included is False


def test_agency_name_in_title_does_not_create_policy_match():
    item = _item("Department for Business, Innovation, Science and Trade")

    assert apply_topic_filter([item]) == []


def test_recent_false_negative_terms_are_in_default_profile():
    items = [
        _item("Digital sovereignty and public services", link="https://example.com/digital-sovereignty"),
        _item("Digital ID in the UK", link="https://example.com/digital-id"),
        _item("Illegal intimate images and deepfakes", link="https://example.com/deepfakes"),
        _item("Mobile platform conduct requirements", link="https://example.com/mobile-platforms"),
    ]

    filtered = apply_topic_filter(items)

    assert {item.title for item in filtered} == {item.title for item in items}
