use crate::{FilterProfile, KeywordStrength, NewsItem, ParliamentBriefing};
use std::collections::{BTreeMap, BTreeSet};

const BOILERPLATE_PATTERNS: &[&str] = &[
    " is the uk's communications regulator",
    " is the uk's independent authority",
    " is responsible for ",
    "we are responsible for",
    "find out more about ",
    "follow us on ",
    "subscribe to ",
    "contact the press office",
    "published by ",
];
const BOILERPLATE_PHRASES: &[&str] = &[
    "Department for Business, Innovation, Science and Trade",
    "Department for Science, Innovation and Technology",
    "Department for Digital, Culture, Media and Sport",
    "Department for Science, Innovation & Technology",
    "Department for Culture, Media and Sport",
    "Government Digital Service",
    "AI Security Institute",
    "AI Safety Institute",
];

fn contains(text: &str, phrase: &str) -> bool {
    let text = text.to_lowercase();
    let phrase = phrase.to_lowercase();
    if phrase.chars().all(|c| c.is_ascii_alphanumeric()) && phrase.len() <= 3 {
        text.split(|c: char| !c.is_ascii_alphanumeric())
            .any(|word| word == phrase)
    } else {
        text.contains(&phrase)
    }
}

struct ScoreOutcome {
    topics: Vec<String>,
    core: Vec<String>,
    general: Vec<String>,
    supporting: Vec<String>,
    score: i32,
    level: String,
    title_strengths: BTreeMap<String, String>,
    summary_strengths: BTreeMap<String, String>,
    synonyms: Vec<String>,
}

#[derive(Clone)]
struct KeywordHit {
    topic: String,
    phrase: String,
    strength: KeywordStrength,
}

fn score_text(title: &str, summary: &str, profile: &FilterProfile) -> ScoreOutcome {
    let title = strip_boilerplate(title);
    let summary = strip_boilerplate(summary);
    let mut title_matches = vec![];
    let mut summary_matches = vec![];
    let mut synonyms = BTreeSet::new();
    for topic in &profile.topics {
        for keyword in &topic.keywords {
            for synonym in &keyword.synonyms {
                if contains(&title, synonym) || contains(&summary, synonym) {
                    synonyms.insert(synonym.clone());
                }
            }
            let title_variant = std::iter::once(&keyword.phrase)
                .chain(keyword.synonyms.iter())
                .find(|variant| contains(&title, variant));
            let summary_variant = std::iter::once(&keyword.phrase)
                .chain(keyword.synonyms.iter())
                .find(|variant| contains(&summary, variant));
            if title_variant.is_some() {
                title_matches.push(KeywordHit {
                    topic: topic.name.clone(),
                    phrase: keyword.phrase.clone(),
                    strength: keyword.strength.clone(),
                });
            }
            if summary_variant.is_some() {
                summary_matches.push(KeywordHit {
                    topic: topic.name.clone(),
                    phrase: keyword.phrase.clone(),
                    strength: keyword.strength.clone(),
                });
            }
        }
    }

    let title_matches = select_non_overlapping(title_matches);
    let summary_matches = select_non_overlapping(summary_matches);
    let mut topics = BTreeSet::new();
    let mut distinct = BTreeMap::new();
    let mut score = 0;
    let mut ts = BTreeMap::new();
    let mut ss = BTreeMap::new();

    for hit in title_matches {
        let (name, title_weight, _) = strength_metadata(&hit.strength);
        topics.insert(hit.topic);
        score += title_weight;
        ts.insert(hit.phrase.clone(), name.into());
        distinct.insert(hit.phrase, name.to_string());
    }
    for hit in summary_matches {
        let (name, _, summary_weight) = strength_metadata(&hit.strength);
        topics.insert(hit.topic);
        if !(hit.strength == KeywordStrength::Supporting && ts.contains_key(&hit.phrase)) {
            score += summary_weight;
        }
        ss.insert(hit.phrase.clone(), name.into());
        distinct.insert(hit.phrase, name.to_string());
    }
    let core = by_strength(&distinct, "core");
    let general = by_strength(&distinct, "general");
    let supporting = by_strength(&distinct, "supporting");
    let distinct_count = core.len() + general.len() + supporting.len();
    if distinct_count >= 2 {
        score += 1;
    }
    let topics: Vec<String> = topics.into_iter().collect();
    if topics.len() >= 2 {
        score += 1;
    }
    let level = if score >= 8 {
        "高"
    } else if score >= 5 {
        "中"
    } else {
        "低"
    }
    .to_string();
    ScoreOutcome {
        topics,
        core,
        general,
        supporting,
        score,
        level,
        title_strengths: ts,
        summary_strengths: ss,
        synonyms: synonyms.into_iter().collect(),
    }
}

fn strength_metadata(strength: &KeywordStrength) -> (&'static str, i32, i32) {
    match strength {
        KeywordStrength::Core => ("core", 6, 4),
        KeywordStrength::General => ("general", 4, 3),
        KeywordStrength::Supporting => ("supporting", 2, 1),
    }
}

fn by_strength(matches: &BTreeMap<String, String>, strength: &str) -> Vec<String> {
    let mut selected: Vec<String> = matches
        .iter()
        .filter(|(_, matched_strength)| matched_strength.as_str() == strength)
        .map(|(phrase, _)| phrase.clone())
        .collect();
    selected.sort_by_key(|x| x.to_lowercase());
    selected
}

fn select_non_overlapping(mut matches: Vec<KeywordHit>) -> Vec<KeywordHit> {
    matches.sort_by(|a, b| {
        b.phrase
            .len()
            .cmp(&a.phrase.len())
            .then_with(|| a.phrase.to_lowercase().cmp(&b.phrase.to_lowercase()))
    });
    let mut selected: Vec<KeywordHit> = vec![];
    for hit in matches {
        if selected
            .iter()
            .any(|existing| phrase_contains(&existing.phrase, &hit.phrase))
        {
            continue;
        }
        selected.push(hit);
    }
    selected
}

fn phrase_contains(longer: &str, shorter: &str) -> bool {
    longer.eq_ignore_ascii_case(shorter) || contains(longer, shorter)
}

fn strip_boilerplate(value: &str) -> String {
    let mut text = value.to_string();
    for phrase in BOILERPLATE_PHRASES {
        text = remove_case_insensitive(&text, phrase);
    }
    if !BOILERPLATE_PATTERNS
        .iter()
        .any(|pattern| text.to_lowercase().contains(pattern))
    {
        return text.trim().to_string();
    }
    let mut retained = vec![];
    for sentence in text.split_terminator(['.', '!', '?']) {
        let sentence = sentence.trim();
        if sentence.is_empty() {
            continue;
        }
        let lowered = sentence.to_lowercase();
        if BOILERPLATE_PATTERNS
            .iter()
            .any(|pattern| lowered.contains(pattern))
        {
            continue;
        }
        retained.push(sentence);
    }
    retained.join(" ")
}

fn remove_case_insensitive(text: &str, phrase: &str) -> String {
    let mut result = text.to_string();
    let phrase = phrase.to_lowercase();
    while let Some(index) = result.to_lowercase().find(&phrase) {
        result.replace_range(index..index + phrase.len(), " ");
    }
    result
}

pub fn assess_news(item: &mut NewsItem, profile: &FilterProfile) -> bool {
    let ScoreOutcome {
        topics,
        core,
        general,
        supporting,
        score,
        level,
        title_strengths: ts,
        summary_strengths: ss,
        synonyms,
    } = score_text(&item.title, &item.summary, profile);
    item.matched_topics = topics;
    item.core_matched_keywords = core;
    item.general_matched_keywords = general;
    item.supporting_matched_keywords = supporting;
    item.matched_keywords = [
        item.core_matched_keywords.clone(),
        item.general_matched_keywords.clone(),
        item.supporting_matched_keywords.clone(),
    ]
    .concat();
    item.title_matched_keywords = ts.keys().cloned().collect();
    item.summary_matched_keywords = ss.keys().cloned().collect();
    item.title_keyword_strengths = ts;
    item.summary_keyword_strengths = ss;
    item.matched_synonyms = synonyms;
    item.boolean_score = score;
    item.relevance_score = f64::from(score);
    item.relevance_level = level;
    score >= profile.minimum_score
}

pub fn assess_parliament(item: &mut ParliamentBriefing, profile: &FilterProfile) -> bool {
    let ScoreOutcome {
        topics,
        core,
        general,
        supporting,
        score,
        level,
        ..
    } = score_text(&item.title, &item.summary, profile);
    item.matched_topics = topics;
    item.core_matched_keywords = core;
    item.general_matched_keywords = general;
    item.supporting_matched_keywords = supporting;
    item.matched_keywords = [
        item.core_matched_keywords.clone(),
        item.general_matched_keywords.clone(),
        item.supporting_matched_keywords.clone(),
    ]
    .concat();
    item.boolean_score = score;
    item.relevance_score = f64::from(score);
    item.relevance_level = level;
    score >= profile.minimum_score
}

pub fn apply_hybrid_filter(
    news: &mut [NewsItem],
    parliament: &mut [ParliamentBriefing],
    profile: &FilterProfile,
) -> (Vec<NewsItem>, Vec<ParliamentBriefing>) {
    apply_hybrid_filter_with_topics(news, parliament, profile, None)
}

pub fn apply_hybrid_filter_with_topics(
    news: &mut [NewsItem],
    parliament: &mut [ParliamentBriefing],
    profile: &FilterProfile,
    allowed_topics: Option<&BTreeMap<String, BTreeSet<String>>>,
) -> (Vec<NewsItem>, Vec<ParliamentBriefing>) {
    if profile.ranking_method != "hybrid_bm25" {
        return (
            news.iter_mut()
                .filter_map(|item| assess_news(item, profile).then(|| item.clone()))
                .collect(),
            parliament
                .iter_mut()
                .filter_map(|item| assess_parliament(item, profile).then(|| item.clone()))
                .collect(),
        );
    }
    let documents: Vec<Vec<String>> = news
        .iter()
        .map(|item| document_tokens(&item.title, &item.summary, profile.title_weight))
        .chain(
            parliament
                .iter()
                .map(|item| document_tokens(&item.title, &item.summary, profile.title_weight)),
        )
        .collect();
    if documents.is_empty() {
        return (vec![], vec![]);
    }
    let mut dfs: BTreeMap<String, usize> = BTreeMap::new();
    for document in &documents {
        for token in document.iter().cloned().collect::<BTreeSet<_>>() {
            *dfs.entry(token).or_default() += 1;
        }
    }
    let average = documents.iter().map(Vec::len).sum::<usize>() as f64 / documents.len() as f64;
    let mut filtered_news = vec![];
    let news_len = news.len();
    for (index, item) in news.iter_mut().enumerate() {
        let allowed = item
            .unit_category
            .as_ref()
            .and_then(|source| allowed_topics.and_then(|topics| topics.get(source)));
        if score_hybrid_news(
            item,
            &documents[index],
            &dfs,
            average,
            documents.len(),
            profile,
            allowed,
        ) {
            filtered_news.push(item.clone());
        }
    }
    let mut filtered_parliament = vec![];
    for (index, item) in parliament.iter_mut().enumerate() {
        if score_hybrid_parliament(
            item,
            &documents[news_len + index],
            &dfs,
            average,
            documents.len(),
            profile,
        ) {
            filtered_parliament.push(item.clone());
        }
    }
    filtered_news.sort_by(|a, b| {
        b.bm25_score
            .total_cmp(&a.bm25_score)
            .then_with(|| a.published_at.cmp(&b.published_at))
            .then_with(|| a.title.to_lowercase().cmp(&b.title.to_lowercase()))
            .then_with(|| a.link.cmp(&b.link))
    });
    filtered_parliament.sort_by(|a, b| {
        b.bm25_score
            .total_cmp(&a.bm25_score)
            .then_with(|| a.published_at.cmp(&b.published_at))
            .then_with(|| a.title.to_lowercase().cmp(&b.title.to_lowercase()))
            .then_with(|| a.webpage_url.cmp(&b.webpage_url))
    });
    (filtered_news, filtered_parliament)
}

fn score_hybrid_news(
    item: &mut NewsItem,
    document: &[String],
    dfs: &BTreeMap<String, usize>,
    average: f64,
    count: usize,
    profile: &FilterProfile,
    allowed: Option<&BTreeSet<String>>,
) -> bool {
    if !assess_news(item, profile) {
        return false;
    }
    let scores = topic_scores(
        &item.title,
        &item.summary,
        document,
        dfs,
        average,
        count,
        profile,
        allowed,
    );
    apply_bm25(
        &mut item.matched_topics,
        &mut item.bm25_topic_scores,
        &mut item.bm25_score,
        &mut item.relevance_score,
        &mut item.relevance_level,
        scores,
        profile,
    )
}

fn score_hybrid_parliament(
    item: &mut ParliamentBriefing,
    document: &[String],
    dfs: &BTreeMap<String, usize>,
    average: f64,
    count: usize,
    profile: &FilterProfile,
) -> bool {
    if !assess_parliament(item, profile) {
        return false;
    }
    let scores = topic_scores(
        &item.title,
        &item.summary,
        document,
        dfs,
        average,
        count,
        profile,
        None,
    );
    apply_bm25(
        &mut item.matched_topics,
        &mut item.bm25_topic_scores,
        &mut item.bm25_score,
        &mut item.relevance_score,
        &mut item.relevance_level,
        scores,
        profile,
    )
}

#[allow(clippy::too_many_arguments)]
fn topic_scores(
    title: &str,
    summary: &str,
    document: &[String],
    dfs: &BTreeMap<String, usize>,
    average: f64,
    count: usize,
    profile: &FilterProfile,
    allowed: Option<&BTreeSet<String>>,
) -> BTreeMap<String, f64> {
    let mut scores = BTreeMap::new();
    for topic in &profile.topics {
        if allowed.is_some_and(|topics| !topics.contains(&topic.name)) {
            continue;
        }
        let single = FilterProfile {
            topics: vec![topic.clone()],
            ..profile.clone()
        };
        if score_text(title, summary, &single).score < profile.minimum_score {
            continue;
        }
        let mut query = BTreeMap::new();
        for keyword in &topic.keywords {
            let weight = match keyword.strength {
                KeywordStrength::Core => 3.0_f64,
                KeywordStrength::General => 2.0_f64,
                KeywordStrength::Supporting => 1.0_f64,
            };
            for variant in std::iter::once(&keyword.phrase).chain(keyword.synonyms.iter()) {
                for token in tokenize(variant) {
                    query
                        .entry(token)
                        .and_modify(|value: &mut f64| *value = value.max(weight))
                        .or_insert(weight);
                }
            }
        }
        let frequencies = document
            .iter()
            .cloned()
            .fold(BTreeMap::new(), |mut map, token| {
                *map.entry(token).or_insert(0usize) += 1;
                map
            });
        let ratio = document.len() as f64 / average;
        let mut score = 0.0;
        for (token, weight) in query {
            let frequency = *frequencies.get(&token).unwrap_or(&0) as f64;
            if frequency == 0.0 {
                continue;
            }
            let df = *dfs.get(&token).unwrap_or(&0) as f64;
            let idf = (1.0 + (count as f64 - df + 0.5) / (df + 0.5)).ln();
            score += weight * idf * frequency * (profile.bm25_k1 + 1.0)
                / (frequency + profile.bm25_k1 * (1.0 - profile.bm25_b + profile.bm25_b * ratio));
        }
        scores.insert(topic.name.clone(), (score * 10_000.0).round() / 10_000.0);
    }
    scores
}

fn apply_bm25(
    topics: &mut Vec<String>,
    target: &mut BTreeMap<String, f64>,
    bm25: &mut f64,
    relevance: &mut f64,
    level: &mut String,
    scores: BTreeMap<String, f64>,
    profile: &FilterProfile,
) -> bool {
    let accepted: Vec<String> = profile
        .topics
        .iter()
        .filter(|topic| {
            scores
                .get(&topic.name)
                .is_some_and(|score| *score >= topic.minimum_bm25_score)
        })
        .map(|topic| topic.name.clone())
        .collect();
    if accepted.is_empty() {
        return false;
    }
    *bm25 = accepted
        .iter()
        .filter_map(|topic| scores.get(topic))
        .copied()
        .fold(0.0, f64::max);
    *relevance = *bm25;
    *level = if *bm25 >= 12.0 {
        "高"
    } else if *bm25 >= 8.0 {
        "中"
    } else {
        "低"
    }
    .into();
    *topics = accepted;
    *target = scores;
    true
}

fn document_tokens(title: &str, summary: &str, title_weight: f64) -> Vec<String> {
    let title = tokenize(&strip_boilerplate(title));
    let mut output = vec![];
    for _ in 0..title_weight.round().max(1.0) as usize {
        output.extend(title.clone());
    }
    output.extend(tokenize(&strip_boilerplate(summary)));
    output
}

fn tokenize(value: &str) -> Vec<String> {
    const STOP: &[&str] = &[
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "uk",
        "united",
        "kingdom",
        "government",
        "new",
        "news",
    ];
    value
        .to_lowercase()
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|token| !token.is_empty() && !STOP.contains(token))
        .map(Into::into)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{KeywordDefinition, ProfileTopic};
    fn profile(minimum_score: i32) -> FilterProfile {
        FilterProfile {
            profile_id: "custom-policy".into(),
            name: "Custom".into(),
            description: String::new(),
            version: 1,
            selected_sources: vec!["BIST".into()],
            topics: vec![ProfileTopic {
                name: "Policy".into(),
                keywords: vec![
                    KeywordDefinition {
                        phrase: "alpha framework".into(),
                        strength: KeywordStrength::Core,
                        synonyms: vec![],
                    },
                    KeywordDefinition {
                        phrase: "beta rule".into(),
                        strength: KeywordStrength::General,
                        synonyms: vec![],
                    },
                    KeywordDefinition {
                        phrase: "technology".into(),
                        strength: KeywordStrength::Supporting,
                        synonyms: vec![],
                    },
                ],
                minimum_bm25_score: 0.0,
            }],
            minimum_score,
            ranking_method: "weighted_keywords".into(),
            bm25_k1: 1.2,
            bm25_b: 0.75,
            title_weight: 2.0,
        }
    }
    #[test]
    fn weighted_score_matches_python() {
        let result = score_text(
            "Alpha framework and technology",
            "The beta rule applies.",
            &profile(10),
        );
        assert_eq!(result.score, 12);
        assert_eq!(result.core, vec!["alpha framework"]);
        assert_eq!(result.general, vec!["beta rule"]);
        assert_eq!(result.supporting, vec!["technology"]);
    }
    #[test]
    fn broad_word_alone_stays_below_threshold() {
        assert_eq!(score_text("Technology update", "", &profile(3)).score, 2);
    }

    #[test]
    fn supporting_keyword_repeated_in_title_and_summary_counts_once() {
        let result = score_text(
            "Technology update",
            "Technology programme details.",
            &profile(3),
        );
        assert_eq!(result.score, 2);
    }

    #[test]
    fn overlapping_keywords_keep_the_longest_phrase() {
        let p = FilterProfile {
            profile_id: "overlap".into(),
            name: "Overlap".into(),
            description: String::new(),
            version: 1,
            selected_sources: vec!["GDS".into()],
            topics: vec![ProfileTopic {
                name: "Policy".into(),
                keywords: vec![
                    KeywordDefinition {
                        phrase: "GOV.UK One Login".into(),
                        strength: KeywordStrength::Core,
                        synonyms: vec![],
                    },
                    KeywordDefinition {
                        phrase: "One Login".into(),
                        strength: KeywordStrength::Core,
                        synonyms: vec![],
                    },
                ],
                minimum_bm25_score: 0.0,
            }],
            minimum_score: 3,
            ranking_method: "weighted_keywords".into(),
            bm25_k1: 1.2,
            bm25_b: 0.75,
            title_weight: 2.0,
        };
        let result = score_text("GOV.UK One Login roadmap published", "", &p);
        assert_eq!(result.core, vec!["GOV.UK One Login"]);
    }

    #[test]
    fn boilerplate_is_removed_before_scoring() {
        let p = FilterProfile {
            profile_id: "boilerplate".into(),
            name: "Boilerplate".into(),
            description: String::new(),
            version: 1,
            selected_sources: vec!["BIST".into()],
            topics: vec![ProfileTopic {
                name: "Policy".into(),
                keywords: vec![KeywordDefinition {
                    phrase: "technology".into(),
                    strength: KeywordStrength::General,
                    synonyms: vec![],
                }],
                minimum_bm25_score: 0.0,
            }],
            minimum_score: 3,
            ranking_method: "weighted_keywords".into(),
            bm25_k1: 1.2,
            bm25_b: 0.75,
            title_weight: 2.0,
        };
        assert_eq!(
            score_text(
                "Department for Business, Innovation, Science and Trade",
                "The Department for Business and Trade is responsible for technology policy.",
                &p,
            )
            .score,
            0
        );
    }
}
