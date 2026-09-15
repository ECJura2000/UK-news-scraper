use crate::{NewsItem, ParliamentBriefing, RunStatus};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

pub const DATA_FINGERPRINT_VERSION: &str = "v4";

fn sorted_casefold(values: &[String]) -> Vec<String> {
    let mut out = values.to_vec();
    out.sort_by_cached_key(|value| value.to_lowercase());
    out
}

pub fn make_data_fingerprint(news: &[NewsItem], parliament: &[ParliamentBriefing]) -> String {
    let mut records: Vec<Value> = news
        .iter()
        .map(|item| {
            let mut matched_topics = item.matched_topics.clone();
            matched_topics.sort();
            json!({
                "type": "news", "agency": item.agency, "agency_en": item.agency_en,
                "unit_category": item.unit_category, "content_type": item.content_type.to_string(),
                "date": item.date_text(), "title": item.title, "summary": item.summary,
                "link": item.link, "source_feed": item.source_feed,
                "matched_topics": matched_topics,
                "matched_keywords": sorted_casefold(&item.matched_keywords),
                "core_matched_keywords": sorted_casefold(&item.core_matched_keywords),
                "general_matched_keywords": sorted_casefold(&item.general_matched_keywords),
                "supporting_matched_keywords": sorted_casefold(&item.supporting_matched_keywords),
                "boolean_score": item.boolean_score,
                "bm25_score": item.bm25_score,
                "bm25_topic_scores": item.bm25_topic_scores,
                "matched_synonyms": sorted_casefold(&item.matched_synonyms),
                "publisher_organisation": item.publisher_organisation,
                "responsibility_owner": item.responsibility_owner,
            })
        })
        .collect();
    records.extend(parliament.iter().map(|item| {
        let mut topics = item.topics.clone();
        topics.sort();
        let mut matched_topics = item.matched_topics.clone();
        matched_topics.sort();
        json!({
            "type": "parliament", "publisher": item.publisher, "chamber": item.chamber,
            "date": item.date_text(), "identifier": item.identifier,
            "document_type": item.document_type, "title": item.title, "summary": item.summary,
            "webpage_url": item.webpage_url, "pdf_url": item.pdf_url,
            "fetched_from": item.fetched_from,
            "topics": topics,
            "matched_topics": matched_topics,
            "matched_keywords": sorted_casefold(&item.matched_keywords),
            "core_matched_keywords": sorted_casefold(&item.core_matched_keywords),
            "general_matched_keywords": sorted_casefold(&item.general_matched_keywords),
            "supporting_matched_keywords": sorted_casefold(&item.supporting_matched_keywords),
            "boolean_score": item.boolean_score,
            "bm25_score": item.bm25_score,
            "bm25_topic_scores": item.bm25_topic_scores,
            "matched_synonyms": sorted_casefold(&item.matched_synonyms),
            "publisher_organisation": item.publisher_organisation,
            "responsibility_owner": item.responsibility_owner,
        })
    }));
    records.sort_by_key(|record| serde_json::to_string(record).expect("record JSON"));
    let payload =
        serde_json::to_vec(&json!({"schema": DATA_FINGERPRINT_VERSION, "records": records}))
            .expect("fingerprint JSON");
    format!("{:x}", Sha256::digest(payload))
}

pub fn make_delivery_id(run_id: &str, status: RunStatus, fingerprint: &str) -> String {
    format!(
        "{run_id}:{status}:{}",
        &fingerprint[..fingerprint.len().min(16)]
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{NewsItem, ParliamentBriefing};
    use serde::Deserialize;
    #[test]
    fn empty_fingerprint_is_stable() {
        assert_eq!(
            make_data_fingerprint(&[], &[]),
            "ae737d3e64a45539a3b3df5633d92424a9f67d2b74f4109d7267d029cab39743"
        );
    }

    #[test]
    fn python_v4_golden_vector_matches() {
        #[derive(Deserialize)]
        struct Golden {
            expected: String,
            news: Vec<NewsItem>,
            parliament: Vec<ParliamentBriefing>,
        }
        let fixture = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../tests/fixtures/fingerprint_v4_golden.json");
        let golden: Golden =
            serde_json::from_str(&std::fs::read_to_string(fixture).unwrap()).unwrap();
        assert_eq!(
            make_data_fingerprint(&golden.news, &golden.parliament),
            golden.expected
        );
    }
}
