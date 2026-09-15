from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import math
import re
from typing import TypeVar

from .models import NewsItem, ParliamentBriefing
from .profiles import FilterProfile, HYBRID_BM25, KeywordStrength, default_profile
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
BM25_QUERY_WEIGHTS = {
    KeywordStrength.CORE: 3.0,
    KeywordStrength.GENERAL: 2.0,
    KeywordStrength.SUPPORTING: 1.0,
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
    "Science and Innovation Network",
    "Government Digital Service",
    "AI Security Institute",
    "AI Safety Institute",
)
STOP_WORDS = frozenset(
    "a an and are as at be been being by for from has have in into is it its of on or "
    "that the their this to was were will with uk united kingdom government new news".split()
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_Item = TypeVar("_Item", NewsItem, ParliamentBriefing)


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
    topic_scores: dict[str, int]
    matched_synonyms: tuple[str, ...]


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
    matched_synonyms: set[str] = set()

    for topic in active_profile.topics:
        for keyword in topic.keywords:
            for synonym in keyword.synonyms:
                if keyword_in_text(synonym, normalized_title) or keyword_in_text(synonym, normalized_summary):
                    matched_synonyms.add(synonym)
            title_variant = _first_matching_variant(keyword.phrase, keyword.synonyms, normalized_title)
            summary_variant = _first_matching_variant(keyword.phrase, keyword.synonyms, normalized_summary)
            if title_variant:
                title_matches.append((topic.name, keyword.phrase, keyword.strength))
            if summary_variant:
                summary_matches.append((topic.name, keyword.phrase, keyword.strength))

    title_topics, title_strengths = _select_non_overlapping_matches(title_matches)
    summary_topics, summary_strengths = _select_non_overlapping_matches(summary_matches)
    matched_topics = title_topics | summary_topics
    topic_scores = {
        topic.name: _boolean_score_for_topic(topic.name, title_matches, summary_matches)
        for topic in active_profile.topics
    }
    topic_scores = {name: score for name, score in topic_scores.items() if score}
    score = _boolean_score(title_strengths, summary_strengths, len(matched_topics))
    distinct_keywords = set(title_strengths) | set(summary_strengths)
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
        topic_scores=topic_scores,
        matched_synonyms=tuple(sorted(matched_synonyms, key=str.casefold)),
    )


def apply_profile_filter(
    items: list[_Item],
    profile: FilterProfile | None = None,
) -> list[_Item]:
    active_profile = profile or default_profile()
    return _apply_boolean_filter(items, active_profile)


def apply_profile_filter_collections(
    news_items: list[NewsItem],
    parliament_items: list[ParliamentBriefing],
    profile: FilterProfile | None = None,
    allowed_topics_by_source: dict[str, frozenset[str]] | None = None,
) -> tuple[list[NewsItem], list[ParliamentBriefing]]:
    """Filter both source groups with one shared BM25 corpus and IDF."""
    active_profile = profile or default_profile()
    if active_profile.ranking_method != HYBRID_BM25:
        return (
            _apply_boolean_filter(news_items, active_profile),
            _apply_boolean_filter(parliament_items, active_profile),
        )
    combined: list[NewsItem | ParliamentBriefing] = [*news_items, *parliament_items]
    filtered = _apply_hybrid_filter(combined, active_profile, allowed_topics_by_source)
    news_ids = {id(item) for item in news_items}
    return (
        [item for item in filtered if id(item) in news_ids],
        [item for item in filtered if id(item) not in news_ids],
    )


def relevance_level(score: float) -> str:
    if score >= 12:
        return "高"
    if score >= 8:
        return "中"
    return "低"


def _apply_boolean_filter(items: list[_Item], profile: FilterProfile) -> list[_Item]:
    filtered: list[_Item] = []
    for item in items:
        assessment = assess_relevance(item.title, item.summary, profile)
        if not assessment.included:
            continue
        _apply_assessment(item, assessment)
        item.relevance_score = float(assessment.score)
        item.relevance_level = assessment.level
        filtered.append(item)
    return filtered


def _apply_hybrid_filter(
    items: list[_Item],
    profile: FilterProfile,
    allowed_topics_by_source: dict[str, frozenset[str]] | None = None,
) -> list[_Item]:
    if not items:
        return []
    documents = [_document_tokens(item, profile.title_weight) for item in items]
    document_frequencies = Counter(token for document in documents for token in set(document))
    average_length = sum(map(len, documents)) / len(documents)
    filtered: list[_Item] = []

    for item, tokens in zip(items, documents, strict=True):
        assessment = assess_relevance(item.title, item.summary, profile)
        if not assessment.included:
            continue
        topic_scores: dict[str, float] = {}
        source_id = item.unit_category if isinstance(item, NewsItem) else None
        allowed_topics = (
            allowed_topics_by_source.get(source_id)
            if allowed_topics_by_source is not None and source_id is not None
            else None
        )
        for topic in profile.topics:
            if allowed_topics is not None and topic.name not in allowed_topics:
                continue
            if assessment.topic_scores.get(topic.name, 0) < profile.minimum_score:
                continue
            score = _bm25_score(
                tokens,
                _topic_query_weights(topic.keywords),
                document_frequencies,
                len(documents),
                average_length,
                profile.bm25_k1,
                profile.bm25_b,
            )
            topic_scores[topic.name] = _quantize_score(score)
        accepted_topics = [
            topic.name
            for topic in profile.topics
            if topic.name in topic_scores
            and topic_scores[topic.name] >= topic.minimum_bm25_score
        ]
        if not accepted_topics:
            continue
        _apply_assessment(item, assessment)
        item.matched_topics = accepted_topics
        item.bm25_topic_scores = topic_scores
        item.bm25_score = max(topic_scores[name] for name in accepted_topics)
        item.relevance_score = item.bm25_score
        item.relevance_level = relevance_level(item.bm25_score)
        filtered.append(item)
    return sorted(
        filtered,
        key=lambda item: (-item.bm25_score, item.published_at, item.title.casefold(), _item_url(item)),
    )


def _apply_assessment(item: _Item, assessment: RelevanceAssessment) -> None:
    item.matched_topics = list(assessment.topics)
    item.matched_keywords = list(assessment.keywords)
    item.title_matched_keywords = list(assessment.title_keywords)
    item.summary_matched_keywords = list(assessment.summary_keywords)
    item.core_matched_keywords = list(assessment.core_keywords)
    item.general_matched_keywords = list(assessment.general_keywords)
    item.supporting_matched_keywords = list(assessment.supporting_keywords)
    item.title_keyword_strengths = dict(assessment.title_strengths)
    item.summary_keyword_strengths = dict(assessment.summary_strengths)
    item.boolean_score = assessment.score
    item.matched_synonyms = list(assessment.matched_synonyms)


def _boolean_score(
    title_strengths: dict[str, str],
    summary_strengths: dict[str, str],
    matched_topic_count: int,
) -> int:
    score = sum(TITLE_WEIGHTS[KeywordStrength(value)] for value in title_strengths.values())
    score += sum(
        SUMMARY_WEIGHTS[KeywordStrength(value)]
        for keyword, value in summary_strengths.items()
        if not (KeywordStrength(value) is KeywordStrength.SUPPORTING and keyword in title_strengths)
    )
    distinct_keywords = set(title_strengths) | set(summary_strengths)
    if len({keyword.casefold() for keyword in distinct_keywords}) >= 2:
        score += 1
    if matched_topic_count >= 2:
        score += 1
    return score


def _boolean_score_for_topic(
    topic_name: str,
    title_matches: list[tuple[str, str, KeywordStrength]],
    summary_matches: list[tuple[str, str, KeywordStrength]],
) -> int:
    _, title_strengths = _select_non_overlapping_matches(
        [match for match in title_matches if match[0] == topic_name]
    )
    _, summary_strengths = _select_non_overlapping_matches(
        [match for match in summary_matches if match[0] == topic_name]
    )
    return _boolean_score(title_strengths, summary_strengths, 1 if title_strengths or summary_strengths else 0)


def _topic_query_weights(keywords) -> dict[str, float]:
    weights: dict[str, float] = {}
    for keyword in keywords:
        weight = BM25_QUERY_WEIGHTS[keyword.strength]
        for variant in (keyword.phrase, *keyword.synonyms):
            for token in _tokenize(variant):
                weights[token] = max(weights.get(token, 0.0), weight)
    return weights


def _document_tokens(item: _Item, title_weight: float) -> list[str]:
    title_tokens = _tokenize(_strip_boilerplate(item.title))
    summary_tokens = _tokenize(_strip_boilerplate(item.summary))
    repetitions = max(1, int(round(title_weight)))
    return title_tokens * repetitions + summary_tokens


def _tokenize(value: str) -> list[str]:
    return [
        token
        for token in _TOKEN_PATTERN.findall(normalize_for_match(value).casefold())
        if token not in STOP_WORDS
    ]


def _bm25_score(
    document: list[str],
    query_weights: dict[str, float],
    document_frequencies: Counter[str],
    document_count: int,
    average_length: float,
    k1: float,
    b: float,
) -> float:
    frequencies = Counter(document)
    length_ratio = len(document) / average_length if average_length else 0.0
    score = 0.0
    for token, query_weight in query_weights.items():
        frequency = frequencies.get(token, 0)
        if not frequency:
            continue
        document_frequency = document_frequencies[token]
        inverse_document_frequency = math.log(
            1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        denominator = frequency + k1 * (1.0 - b + b * length_ratio)
        score += query_weight * inverse_document_frequency * frequency * (k1 + 1.0) / denominator
    return score


def _quantize_score(score: float) -> float:
    return float(Decimal(str(score)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _first_matching_variant(phrase: str, synonyms: tuple[str, ...], text: str) -> str:
    for variant in (phrase, *synonyms):
        if keyword_in_text(variant, text):
            return variant
    return ""


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


def _item_url(item: NewsItem | ParliamentBriefing) -> str:
    return item.link if isinstance(item, NewsItem) else item.webpage_url
