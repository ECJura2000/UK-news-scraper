from datetime import datetime, timezone

from UK_news_scraper.dedupe import dedupe_news_items
from UK_news_scraper.excel_exporter import _dedupe_for_export
from UK_news_scraper.models import NewsItem


def _item(link: str) -> NewsItem:
    return NewsItem(
        agency="Agency",
        agency_en="Agency",
        unit_category="A",
        title="Same title",
        link=link,
        published_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )


def test_fetch_and_export_use_same_dedupe_contract():
    items = [_item("https://example.com/a"), _item("https://example.com/b")]

    assert len(dedupe_news_items(items)) == 2
    assert _dedupe_for_export(items) == dedupe_news_items(items)


def test_duplicate_link_is_removed():
    assert len(dedupe_news_items([_item("https://example.com/a"), _item("https://example.com/a/")])) == 1
