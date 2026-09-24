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
    for topic in &profile.topics {
        for keyword in &topic.keywords {
            if contains(&title, &keyword.phrase) {
                title_matches.push(KeywordHit {
                    topic: topic.name.clone(),
                    phrase: keyword.phrase.clone(),
                    strength: keyword.strength.clone(),
                });
            }
            if contains(&summary, &keyword.phrase) {
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
    item.matched_keywords
        .sort_by_cached_key(|word| word.to_lowercase());
    item.title_matched_keywords = ts.keys().cloned().collect();
    item.summary_matched_keywords = ss.keys().cloned().collect();
    item.title_keyword_strengths = ts;
    item.summary_keyword_strengths = ss;
    item.relevance_score = score;
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
        title_strengths: ts,
        summary_strengths: ss,
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
    item.matched_keywords
        .sort_by_cached_key(|word| word.to_lowercase());
    item.title_matched_keywords = ts.keys().cloned().collect();
    item.summary_matched_keywords = ss.keys().cloned().collect();
    item.relevance_score = score;
    item.relevance_level = level;
    score >= profile.minimum_score
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
                    },
                    KeywordDefinition {
                        phrase: "beta rule".into(),
                        strength: KeywordStrength::General,
                    },
                    KeywordDefinition {
                        phrase: "technology".into(),
                        strength: KeywordStrength::Supporting,
                    },
                ],
            }],
            minimum_score,
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
                    },
                    KeywordDefinition {
                        phrase: "One Login".into(),
                        strength: KeywordStrength::Core,
                    },
                ],
            }],
            minimum_score: 3,
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
                }],
            }],
            minimum_score: 3,
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
