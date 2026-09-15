from datetime import datetime, timezone
import json
from pathlib import Path

from UK_news_scraper.models import NewsItem, SourceHealth
from UK_news_scraper.organisations import (
    apply_organisation_metadata,
    audit_content_api_publishers,
    audit_organisation_state,
)
from UK_news_scraper.profiles import default_profile
from UK_news_scraper.relevance import apply_profile_filter_collections, assess_relevance


def _item(title: str, index: int, agency: str = "BIST", agency_en: str = "Department for Business, Innovation, Science and Trade") -> NewsItem:
    return NewsItem(
        agency=agency,
        agency_en=agency_en,
        unit_category=agency,
        title=title,
        link=f"https://example.test/{index}",
        published_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )


def test_word_examples_pass_shared_corpus_hybrid_filter():
    items = [
        _item("UK artificial intelligence sectoral analysis survey", 0),
        _item("Online safety industry bulletin", 1),
        *[_item(f"Routine departmental update number {index}", index + 2) for index in range(40)],
    ]

    filtered, parliament = apply_profile_filter_collections(items, [], default_profile())

    assert parliament == []
    assert {item.title for item in filtered} == {
        "UK artificial intelligence sectoral analysis survey",
        "Online safety industry bulletin",
    }
    assert all(item.bm25_score == round(item.bm25_score, 4) for item in filtered)


def test_python_matches_shared_bm25_parity_vector():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "hybrid_bm25_parity.json").read_text()
    )
    profile = default_profile()
    items = [_item(title, index) for index, title in enumerate(fixture["titles"])]

    filtered, _ = apply_profile_filter_collections(items, [], profile)

    # The shared fixture uses the built-in profile and therefore exercises its full query vocabulary.
    assert {item.title: item.bm25_score for item in filtered} == fixture["expected"]


def test_synonym_and_canonical_form_count_as_one_boolean_concept():
    assessment = assess_relevance(
        "AI and artificial intelligence policy",
        "Artificial intelligence strategy",
        default_profile(),
    )

    assert assessment.keywords.count("artificial intelligence") == 1
    assert "AI" in assessment.matched_synonyms


def test_dsit_publisher_is_preserved_and_owner_follows_topics():
    item = _item(
        "AI cyber and semiconductor policy",
        1,
        agency="DSIT Transition",
        agency_en="Department for Science, Innovation and Technology",
    )
    item.matched_topics = ["AI", "網路安全/資安", "半導體/量子技術"]

    apply_organisation_metadata([item])

    assert item.publisher_organisation == "Department for Science, Innovation and Technology"
    assert item.responsibility_owner == "BIST / DCMS / Cabinet Office"


def test_unknown_publisher_and_failed_transition_are_degraded():
    item = _item("Artificial intelligence policy", 1)
    item.publisher_organisation = "Unexpected Technology Ministry"
    health = (
        SourceHealth("DSIT Transition", True, False, 0, 0.1, warning="feed unavailable"),
    )

    status, changes = audit_organisation_state([item], health)

    assert status == "degraded"
    assert "unknown_publisher:Unexpected Technology Ministry" in changes
    assert "transitional_source_unavailable:DSIT Transition" in changes


def test_content_api_publisher_overrides_registry_assumption(monkeypatch):
    item = _item("Artificial intelligence policy", 1)
    item.link = "https://www.gov.uk/government/news/ai-policy"
    item.source_feed = "https://www.gov.uk/government/organisations/department-for-science-innovation-and-technology.atom"
    monkeypatch.setattr(
        "UK_news_scraper.organisations.get_text",
        lambda _url: '{"links":{"organisations":[{"title":"Department for Science, Innovation and Technology"}]}}',
    )

    changes = audit_content_api_publishers([item])

    assert changes == ()
    assert item.publisher_organisation == "Department for Science, Innovation and Technology"
