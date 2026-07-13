from datetime import datetime, timezone

from UK_news_scraper.models import NewsItem
from UK_news_scraper.scrapers.ministry.registry import apply_topic_filter


def _item(title: str, summary: str = "") -> NewsItem:
    return NewsItem("Agency", "Agency", "A", title, "https://example.com", datetime.now(timezone.utc), summary)


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
