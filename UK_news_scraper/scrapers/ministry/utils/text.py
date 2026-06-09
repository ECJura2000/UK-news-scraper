from __future__ import annotations

import html
import re
from bs4 import BeautifulSoup


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"([A-Za-z])\s*[’‘']\s*(s|t|re|ve|ll|d|m)\b",
        r"\1'\2",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"([A-Za-z])[’‘]([A-Za-z])", r"\1'\2", text)


def normalize_for_match(value: str) -> str:
    return f" {clean_text(value).casefold()} "


def keyword_in_text(keyword: str, text: str) -> bool:
    normalized_keyword = keyword.casefold().strip()
    if not normalized_keyword:
        return False
    if len(normalized_keyword) <= 3 and normalized_keyword.isascii():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])", text))
    return normalized_keyword in text
