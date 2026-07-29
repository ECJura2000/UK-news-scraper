from __future__ import annotations

from dataclasses import dataclass

from .models import NewsItem, ParliamentBriefing
from .profiles import FilterProfile, KeywordStrength, default_profile
from .scrapers.ministry.utils.text import keyword_in_text, normalize_for_match


TITLE_WEIGHTS = {
    KeywordStrength.CORE: 6,
    KeywordStrength.GENERAL: 4,
    KeywordStrength.SUPPORTING: 2,
}
SUMMARY_WEIGHTS = {
    KeywordStrength.CORE: 4,
    KeywordStrength.GENERAL: 3,
    KeywordStrength.SUPPORTING: 1,
}


@dataclass(frozen=True)
class RelevanceAssessment:
    topics: tuple[str, ...]
    keywords: tuple[str, ...]
    title_keywords: tuple[str, ...]
    summary_keywords: tuple[str, ...]
    core_keywords: tuple[str, ...]
    general_keywords: tuple[str, ...]
    supporting_keywords: tuple[str, ...]
    title_strengths: dict[str, str]
    summary_strengths: dict[str, str]
    score: int
    level: str
    included: bool


def assess_relevance(
    title: str,
    summary: str,
    profile: FilterProfile | None = None,
) -> RelevanceAssessment:
    active_profile = profile or default_profile()
    normalized_title = normalize_for_match(title)
    normalized_summary = normalize_for_match(summary)
    title_strengths: dict[str, str] = {}
    summary_strengths: dict[str, str] = {}
    matched_topics: set[str] = set()

    for topic in active_profile.topics:
        topic_matched = False
        for keyword in topic.keywords:
            if keyword_in_text(keyword.phrase, normalized_title):
                title_strengths[keyword.phrase] = keyword.strength.value
                topic_matched = True
            if keyword_in_text(keyword.phrase, normalized_summary):
                summary_strengths[keyword.phrase] = keyword.strength.value
                topic_matched = True
        if topic_matched:
            matched_topics.add(topic.name)

    score = sum(
        TITLE_WEIGHTS[KeywordStrength(strength)]
        for strength in title_strengths.values()
    )
    score += sum(
        SUMMARY_WEIGHTS[KeywordStrength(strength)]
        for strength in summary_strengths.values()
    )
    distinct_keywords = set(title_strengths) | set(summary_strengths)
    if len({keyword.casefold() for keyword in distinct_keywords}) >= 2:
        score += 1
    if len(matched_topics) >= 2:
        score += 1

    by_strength = {
        strength: tuple(
            sorted(
                keyword
                for keyword in distinct_keywords
                if title_strengths.get(keyword) == strength.value
                or summary_strengths.get(keyword) == strength.value
            )
        )
        for strength in KeywordStrength
    }
    return RelevanceAssessment(
        topics=tuple(sorted(matched_topics)),
        keywords=tuple(sorted(distinct_keywords, key=str.casefold)),
        title_keywords=tuple(sorted(title_strengths, key=str.casefold)),
        summary_keywords=tuple(sorted(summary_strengths, key=str.casefold)),
        core_keywords=by_strength[KeywordStrength.CORE],
        general_keywords=by_strength[KeywordStrength.GENERAL],
        supporting_keywords=by_strength[KeywordStrength.SUPPORTING],
        title_strengths=title_strengths,
        summary_strengths=summary_strengths,
        score=score,
        level=relevance_level(score),
        included=score >= active_profile.minimum_score,
    )


def apply_profile_filter(
    items: list[NewsItem] | list[ParliamentBriefing],
    profile: FilterProfile | None = None,
):
    active_profile = profile or default_profile()
    filtered = []
    for item in items:
        assessment = assess_relevance(item.title, item.summary, active_profile)
        if not assessment.included:
            continue
        item.matched_topics = list(assessment.topics)
        item.matched_keywords = list(assessment.keywords)
        item.title_matched_keywords = list(assessment.title_keywords)
        item.summary_matched_keywords = list(assessment.summary_keywords)
        item.core_matched_keywords = list(assessment.core_keywords)
        item.general_matched_keywords = list(assessment.general_keywords)
        item.supporting_matched_keywords = list(assessment.supporting_keywords)
        item.title_keyword_strengths = dict(assessment.title_strengths)
        item.summary_keyword_strengths = dict(assessment.summary_strengths)
        item.relevance_score = assessment.score
        item.relevance_level = assessment.level
        filtered.append(item)
    return filtered


def relevance_level(score: int) -> str:
    if score >= 8:
        return "高"
    if score >= 5:
        return "中"
    return "低"
