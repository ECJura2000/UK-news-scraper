use crate::{FilterProfile, KeywordStrength, NewsItem, ParliamentBriefing};
use std::collections::BTreeMap;

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

fn score_text(title: &str, summary: &str, profile: &FilterProfile) -> ScoreOutcome {
    let mut topics = vec![];
    let mut core = vec![];
    let mut general = vec![];
    let mut supporting = vec![];
    let mut score = 0;
    let mut ts = BTreeMap::new();
    let mut ss = BTreeMap::new();
    for topic in &profile.topics {
        let mut topic_hit = false;
        for keyword in &topic.keywords {
            let in_title = contains(title, &keyword.phrase);
            let in_summary = contains(summary, &keyword.phrase);
            if !in_title && !in_summary {
                continue;
            }
            topic_hit = true;
            let (name, title_weight, summary_weight, list) = match keyword.strength {
                KeywordStrength::Core => ("core", 6, 4, &mut core),
                KeywordStrength::General => ("general", 4, 3, &mut general),
                KeywordStrength::Supporting => ("supporting", 2, 1, &mut supporting),
            };
            list.push(keyword.phrase.clone());
            if in_title {
                score += title_weight;
                ts.insert(keyword.phrase.clone(), name.into());
            }
            if in_summary {
                score += summary_weight;
                ss.insert(keyword.phrase.clone(), name.into());
            }
        }
        if topic_hit {
            topics.push(topic.name.clone());
        }
    }
    core.sort_by_cached_key(|x| x.to_lowercase());
    core.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
    general.sort_by_cached_key(|x| x.to_lowercase());
    general.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
    supporting.sort_by_cached_key(|x| x.to_lowercase());
    supporting.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
    let distinct_count = core.len() + general.len() + supporting.len();
    if distinct_count >= 2 {
        score += 1;
    }
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
}
