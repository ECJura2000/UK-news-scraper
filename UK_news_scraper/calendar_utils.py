from __future__ import annotations

from datetime import date
from enum import Enum


ROC_YEAR_OFFSET = 1911
ROC_START_DATE = date(1912, 1, 1)


class CalendarMode(str, Enum):
    GREGORIAN = "gregorian"
    ROC = "roc"

    @property
    def label(self) -> str:
        return "民國" if self is CalendarMode.ROC else "西元"


def gregorian_to_roc(value: date) -> tuple[int, int, int]:
    if value < ROC_START_DATE:
        raise ValueError("1912-01-01 以前不適用民國紀年")
    return value.year - ROC_YEAR_OFFSET, value.month, value.day


def roc_to_gregorian(year: int, month: int, day: int) -> date:
    if year < 1:
        raise ValueError("民國年必須大於等於 1")
    return date(year + ROC_YEAR_OFFSET, month, day)


def format_date(value: date, mode: CalendarMode) -> str:
    if mode is CalendarMode.ROC:
        year, month, day = gregorian_to_roc(value)
        return f"民國{year:03d}年{month:02d}月{day:02d}日"
    return value.isoformat()


def excel_number_format(mode: CalendarMode) -> str:
    if mode is CalendarMode.ROC:
        return '[$-zh-TW-x-roc]e"年"mm"月"dd"日"'
    return "yyyy-mm-dd"


def output_filename(
    period_start: date,
    period_end: date,
    profile_id: str,
    *,
    default_profile_id: str,
) -> str:
    stem = f"{period_start:%Y%m%d}-{period_end:%Y%m%d}_UK新聞查詢"
    if profile_id != default_profile_id:
        stem = f"{stem}_{profile_id}"
    return f"{stem}.xlsx"
