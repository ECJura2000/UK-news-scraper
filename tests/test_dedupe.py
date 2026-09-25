from datetime import datetime, timezone
from dataclasses import replace

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


def test_shared_official_link_keeps_same_agency_regardless_of_fetch_order():
    first = replace(_item("https://www.gov.uk/government/news/shared"), unit_category="govuk:alpha", agency="Alpha")
    second = replace(first, unit_category="govuk:beta", agency="Beta")
    assert dedupe_news_items([first, second])[0].agency == "Alpha"
    assert dedupe_news_items([second, first])[0].agency == "Alpha"
