from hypothesis import given, strategies as st

from UK_news_scraper.dedupe import normalize_title
from UK_news_scraper.scrapers.ministry.utils.date import parse_datetime_text


@given(st.text())
def test_title_normalization_is_idempotent(value):
    normalized = normalize_title(value)
    assert normalize_title(normalized) == normalized


@given(st.text())
def test_date_parser_never_crashes(value):
    result = parse_datetime_text(value)
    assert result is None or result.tzinfo is not None
