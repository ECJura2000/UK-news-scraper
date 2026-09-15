from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RunStatus(str, Enum):
    COMPLETE = "complete"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class TopicRule:
    name: str
    subtopics: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class Agency:
    name_zh: str
    name_en: str
    short_name: str
    homepage: str
    feeds: tuple[str, ...] = ()
    news_pages: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    link_include_patterns: tuple[str, ...] = ()
    official_pages: tuple[str, ...] = ()
    scraper_adapter: str = "generic_rss"
    fallbacks: tuple[str, ...] = ()
    exclude_title_patterns: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        return f"{self.name_zh} ({self.short_name})"


@dataclass
class NewsItem:
    agency: str
    agency_en: str
    unit_category: str | None
    title: str
    link: str
    published_at: datetime
    summary: str = ""
    source_feed: str = ""
    matched_topics: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    title_matched_keywords: list[str] = field(default_factory=list)
    summary_matched_keywords: list[str] = field(default_factory=list)
    core_matched_keywords: list[str] = field(default_factory=list)
    general_matched_keywords: list[str] = field(default_factory=list)
    supporting_matched_keywords: list[str] = field(default_factory=list)
    title_keyword_strengths: dict[str, str] = field(default_factory=dict)
    summary_keyword_strengths: dict[str, str] = field(default_factory=dict)
    relevance_score: float = 0.0
    relevance_level: str = ""
    boolean_score: int = 0
    bm25_score: float = 0.0
    bm25_topic_scores: dict[str, float] = field(default_factory=dict)
    matched_synonyms: list[str] = field(default_factory=list)
    publisher_organisation: str = ""
    responsibility_owner: str = ""
    content_type: str = "news"

    @property
    def date_text(self) -> str:
        return self.published_at.date().isoformat()


@dataclass
class ParliamentBriefing:
    published_at: datetime
    chamber: str
    publisher: str
    title: str
    summary: str
    identifier: str
    webpage_url: str
    pdf_url: str = ""
    topics: list[str] = field(default_factory=list)
    document_type: str = "Research Briefing"
    fetched_from: str = ""
    matched_topics: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    title_matched_keywords: list[str] = field(default_factory=list)
    summary_matched_keywords: list[str] = field(default_factory=list)
    core_matched_keywords: list[str] = field(default_factory=list)
    general_matched_keywords: list[str] = field(default_factory=list)
    supporting_matched_keywords: list[str] = field(default_factory=list)
    title_keyword_strengths: dict[str, str] = field(default_factory=dict)
    summary_keyword_strengths: dict[str, str] = field(default_factory=dict)
    relevance_score: float = 0.0
    relevance_level: str = ""
    boolean_score: int = 0
    bm25_score: float = 0.0
    bm25_topic_scores: dict[str, float] = field(default_factory=dict)
    matched_synonyms: list[str] = field(default_factory=list)
    publisher_organisation: str = "UK Parliament"
    responsibility_owner: str = "UK Parliament"

    @property
    def date_text(self) -> str:
        return self.published_at.date().isoformat()


@dataclass(frozen=True)
class SourceHealth:
    source: str
    critical: bool
    success: bool
    item_count: int
    duration_seconds: float
    newest_published_at: str = ""
    warning: str = ""
