from argparse import Namespace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from UK_news_scraper.main import _date_range_label, _resolve_date_range


def _args(**overrides):
    values = {
        "period": [],
        "since": None,
        "until": None,
        "days": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_default_range_is_stable_across_same_local_day():
    local_timezone = ZoneInfo("Asia/Taipei")
    early = datetime(2026, 6, 8, 7, 1, tzinfo=local_timezone).astimezone(timezone.utc)
    late = datetime(2026, 6, 8, 16, 4, tzinfo=local_timezone).astimezone(timezone.utc)

    early_range = _resolve_date_range(_args(), early)
    late_range = _resolve_date_range(_args(), late)

    assert early_range == late_range
    assert _date_range_label(*early_range, early) == "20260525-20260608"


def test_negative_days_is_rejected():
    with pytest.raises(SystemExit, match="不可為負數"):
        _resolve_date_range(_args(days=-1), datetime.now(timezone.utc))
