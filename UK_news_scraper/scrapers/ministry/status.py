from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ...config import SOURCE_HEALTH_MAX_AGE_DAYS, SOURCE_HEALTH_MIN_ITEMS
from ...models import NewsItem, SourceHealth


@dataclass
class AgencyFetchStatus:
    agency_name: str
    success: bool
    source_name: str = ""
    item_count: int = 0
    attempts: int = 1
    error: str = ""
    duration_seconds: float = 0.0
    newest_published_at: str = ""
    warning: str = ""


@dataclass
class FetchAllResult:
    items: list[NewsItem]
    statuses: list[AgencyFetchStatus] = field(default_factory=list)

    @property
    def all_successful(self) -> bool:
        return all(status.success and not status.warning for status in self.statuses)

    @property
    def failed_statuses(self) -> list[AgencyFetchStatus]:
        return [status for status in self.statuses if not status.success]

    @property
    def source_health(self) -> list[SourceHealth]:
        return [
            SourceHealth(
                source=status.source_name,
                critical=True,
                success=status.success,
                item_count=status.item_count,
                duration_seconds=round(status.duration_seconds, 3),
                newest_published_at=status.newest_published_at,
                warning=status.warning or status.error,
            )
            for status in self.statuses
        ]


def health_warning(source_name: str, items: list[NewsItem], since: datetime) -> str:
    item_count = len(items)
    minimum = SOURCE_HEALTH_MIN_ITEMS.get(source_name, 0)
    if item_count < minimum:
        return f"{source_name} 筆數異常：取得 {item_count} 筆，低於健康門檻 {minimum} 筆"
    maximum_age_days = SOURCE_HEALTH_MAX_AGE_DAYS.get(source_name)
    now = datetime.now(timezone.utc)
    if (
        maximum_age_days is not None
        and items
        and since >= now - timedelta(days=30)
        and max(item.published_at for item in items) < now - timedelta(days=maximum_age_days)
    ):
        return f"{source_name} 最新資料已超過 {maximum_age_days} 天"
    return ""


def newest_published_at(items: list[NewsItem]) -> str:
    if not items:
        return ""
    return max(item.published_at for item in items).isoformat()
