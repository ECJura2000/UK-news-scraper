from __future__ import annotations

import calendar
from datetime import date
import os
import sys
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .calendar_utils import CalendarMode, gregorian_to_roc


COLORS = {
    "paper": "#F7F3E8",
    "surface": "#FFFDF7",
    "ink": "#14213D",
    "muted": "#5C667A",
    "line": "#D8D2C3",
    "accent": "#1B4D5C",
    "core": "#E6A817",
    "general": "#F2C94C",
    "supporting": "#FFF1B8",
    "success": "#2D6A4F",
    "danger": "#A33A32",
}

HIGHLIGHT_PRIORITY = ("supporting", "general", "core")


def enable_high_dpi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def font_family() -> str:
    if sys.platform == "darwin":
        return "PingFang TC"
    if os.name == "nt":
        return "Microsoft JhengHei UI"
    return "Noto Sans CJK TC"


def configure_relevance_tags(text_widget, colors: dict[str, str] = COLORS) -> None:
    for strength in HIGHLIGHT_PRIORITY:
        text_widget.tag_configure(strength, background=colors[strength])
    for strength in HIGHLIGHT_PRIORITY:
        text_widget.tag_raise(strength)


class DateSelector(ttk.Frame):
    def __init__(
        self,
        master,
        value: date,
        command: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self._mode = CalendarMode.GREGORIAN
        self._value = value
        self._command = command
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.day_var = tk.StringVar()
        self.year_box = ttk.Combobox(
            self,
            textvariable=self.year_var,
            state="readonly",
            width=11,
        )
        self.month_box = ttk.Combobox(
            self,
            textvariable=self.month_var,
            state="readonly",
            width=7,
        )
        self.day_box = ttk.Combobox(
            self,
            textvariable=self.day_var,
            state="readonly",
            width=7,
        )
        self.year_box.grid(row=0, column=0, padx=(0, 6))
        self.month_box.grid(row=0, column=1, padx=6)
        self.day_box.grid(row=0, column=2, padx=(6, 0))
        self.year_box.bind("<<ComboboxSelected>>", self._selection_changed)
        self.month_box.bind("<<ComboboxSelected>>", self._selection_changed)
        self.day_box.bind("<<ComboboxSelected>>", self._selection_changed)
        self._refresh()

    def set_mode(self, mode: CalendarMode) -> None:
        self._value = self.get()
        self._mode = mode
        self._refresh()

    def set(self, value: date) -> None:
        self._value = value
        self._refresh()

    def get(self) -> date:
        try:
            year = int(self.year_var.get().replace("民國", "").replace("年", ""))
            month = int(self.month_var.get().replace("月", ""))
            day = int(self.day_var.get().replace("日", ""))
            gregorian_year = year + 1911 if self._mode is CalendarMode.ROC else year
            day = min(day, calendar.monthrange(gregorian_year, month)[1])
            return date(gregorian_year, month, day)
        except ValueError:
            return self._value

    def _refresh(self) -> None:
        current_year = date.today().year + 1
        if self._mode is CalendarMode.ROC:
            years = [
                f"民國{year}年"
                for year in range(1, current_year - 1911 + 1)
            ]
            display_year = gregorian_to_roc(self._value)[0]
            year_value = f"民國{display_year}年"
        else:
            years = [str(year) for year in range(1912, current_year + 1)]
            year_value = str(self._value.year)
        self.year_box["values"] = years
        self.month_box["values"] = [
            f"{month:02d}月" for month in range(1, 13)
        ]
        self.year_var.set(year_value)
        self.month_var.set(f"{self._value.month:02d}月")
        self._refresh_days(self._value.day)

    def _refresh_days(self, preferred_day: int) -> None:
        try:
            year = int(self.year_var.get().replace("民國", "").replace("年", ""))
            month = int(self.month_var.get().replace("月", ""))
            if self._mode is CalendarMode.ROC:
                year += 1911
        except ValueError:
            year, month = self._value.year, self._value.month
        days = calendar.monthrange(year, month)[1]
        self.day_box["values"] = [
            f"{day:02d}日" for day in range(1, days + 1)
        ]
        self.day_var.set(f"{min(preferred_day, days):02d}日")

    def _selection_changed(self, _event=None) -> None:
        previous_day = int(
            self.day_var.get().replace("日", "") or self._value.day
        )
        self._refresh_days(previous_day)
        self._value = self.get()
        if self._command:
            self._command()
