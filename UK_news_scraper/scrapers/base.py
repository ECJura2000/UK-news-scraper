from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import NewsItem


class Scraper(ABC):
    @abstractmethod
    def fetch(self, since: datetime) -> list[NewsItem]:
        raise NotImplementedError
