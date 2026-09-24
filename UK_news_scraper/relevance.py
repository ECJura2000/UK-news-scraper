from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from .models import NewsItem, ParliamentBriefing
from .profiles import FilterProfile, KeywordStrength, default_profile
from .scrapers.ministry.utils.text import clean_text, keyword_in_text, normalize_for_match


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
BOILERPLATE_PATTERNS = (
    " is the uk's communications regulator",
    " is the uk's independent authority",
    " is responsible for ",
    "we are responsible for",
    "find out more about ",
    "follow us on ",
    "subscribe to ",
    "contact the press office",
    "published by ",
)
BOILERPLATE_PHRASES = (
    "Department for Business, Innovation, Science and Trade",
    "Department for Science, Innovation and Technology",
    "Department for Digital, Culture, Media and Sport",
    "Department for Science, Innovation & Technology",
    "Department for Culture, Media and Sport",
    "Government Digital Service",
    "AI Security Institute",
    "AI Safety Institute",
)


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
    normalized_title = normalize_for_match(_strip_boilerplate(title))
    normalized_summary = normalize_for_match(_strip_boilerplate(summary))
    title_matches: list[tuple[str, str, KeywordStrength]] = []
    summary_matches: list[tuple[str, str, KeywordStrength]] = []

    for topic in active_profile.topics:
        for keyword in topic.keywords:
            if keyword_in_text(keyword.phrase, normalized_title):
                title_matches.append((topic.name, keyword.phrase, keyword.strength))
            if keyword_in_text(keyword.phrase, normalized_summary):
                summary_matches.append((topic.name, keyword.phrase, keyword.strength))

    title_topics, title_strengths = _select_non_overlapping_matches(title_matches)
    summary_topics, summary_strengths = _select_non_overlapping_matches(summary_matches)
    matched_topics = title_topics | summary_topics

    score = sum(
        TITLE_WEIGHTS[KeywordStrength(strength)]
        for strength in title_strengths.values()
    )
    distinct_keywords = set(title_strengths) | set(summary_strengths)
    score += sum(
        SUMMARY_WEIGHTS[KeywordStrength(strength)]
        for keyword, strength in summary_strengths.items()
        if not (
            KeywordStrength(strength) is KeywordStrength.SUPPORTING
            and keyword in title_strengths
        )
    )
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
        if isinstance(item, NewsItem):
            path = urlparse(item.link).path.strip("/").split("/")
            if len(path) == 3 and path[:2] == ["government", "organisations"]:
                continue
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


def _select_non_overlapping_matches(
    matches: list[tuple[str, str, KeywordStrength]],
) -> tuple[set[str], dict[str, str]]:
    selected: list[tuple[str, str, KeywordStrength, str]] = []
    for topic, phrase, strength in sorted(
        matches,
        key=lambda match: (-len(_normalized_phrase(match[1])), match[1].casefold()),
    ):
        normalized_phrase = _normalized_phrase(phrase)
        if any(_phrase_contains(existing, normalized_phrase) for *_rest, existing in selected):
            continue
        selected.append((topic, phrase, strength, normalized_phrase))
    return (
        {topic for topic, *_rest in selected},
        {phrase: strength.value for _topic, phrase, strength, _normalized in selected},
    )


def _normalized_phrase(phrase: str) -> str:
    return normalize_for_match(phrase).strip()


def _phrase_contains(longer: str, shorter: str) -> bool:
    return longer == shorter or keyword_in_text(shorter, f" {longer} ")


def _strip_boilerplate(summary: str) -> str:
    text = clean_text(summary)
    if not text:
        return ""
    for phrase in BOILERPLATE_PHRASES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    retained = [
        sentence
        for sentence in sentences
        if not any(pattern in sentence.casefold() for pattern in BOILERPLATE_PATTERNS)
    ]
    return " ".join(retained).strip()
