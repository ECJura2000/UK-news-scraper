from datetime import date

import pytest

from UK_news_scraper.calendar_utils import (
    CalendarMode,
    format_date,
    gregorian_to_roc,
    output_filename,
    roc_to_gregorian,
)
from UK_news_scraper.profiles import DEFAULT_PROFILE_ID


def test_roc_conversion_handles_first_year_and_leap_day():
    assert gregorian_to_roc(date(1912, 1, 1)) == (1, 1, 1)
    assert gregorian_to_roc(date(2024, 2, 29)) == (113, 2, 29)
    assert roc_to_gregorian(113, 2, 29) == date(2024, 2, 29)
    assert format_date(date(2026, 7, 28), CalendarMode.ROC) == "民國115年07月28日"


def test_roc_conversion_rejects_dates_before_1912():
    with pytest.raises(ValueError, match="1912"):
        gregorian_to_roc(date(1911, 12, 31))


def test_output_filename_uses_gregorian_range_and_optional_profile_id():
    start = date(2026, 7, 13)
    end = date(2026, 7, 27)

    assert (
        output_filename(start, end, DEFAULT_PROFILE_ID, default_profile_id=DEFAULT_PROFILE_ID)
        == "20260713-20260727_UK新聞查詢.xlsx"
    )
    assert (
        output_filename(start, end, "digital-health", default_profile_id=DEFAULT_PROFILE_ID)
        == "20260713-20260727_UK新聞查詢_digital-health.xlsx"
    )
