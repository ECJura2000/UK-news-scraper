use serde::{Deserialize, Serialize};
use std::sync::OnceLock;
use uk_news_core::Agency;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CatalogEntry {
    pub id: String,
    pub name_en: String,
    pub name_zh: String,
    pub jurisdiction: String,
    pub kind: String,
    pub homepage: String,
    pub status: String,
    pub adapter: String,
    pub slug: String,
    #[serde(default)]
    pub feed: String,
    #[serde(default)]
    pub news_page: String,
    pub provenance: String,
    pub reason: String,
}

#[derive(Deserialize)]
struct Snapshot {
    schema_version: u32,
    sources: Vec<CatalogEntry>,
}

fn snapshot_entries() -> &'static [CatalogEntry] {
    static SNAPSHOT: OnceLock<Vec<CatalogEntry>> = OnceLock::new();
    SNAPSHOT.get_or_init(|| {
        let snapshot: Snapshot = serde_json::from_str(include_str!(
            "../../../../UK_news_scraper/data/source_catalog.json"
        ))
        .expect("valid official source catalog");
        assert_eq!(snapshot.schema_version, 1);
        snapshot.sources
    })
}

pub fn catalog_entries() -> Vec<CatalogEntry> {
    let mut entries = crate::agencies::legacy_agencies()
        .into_iter()
        .map(|agency| CatalogEntry {
            id: agency.short_name,
            name_en: agency.name_en,
            name_zh: agency.name_zh,
            jurisdiction: "UK".into(),
            kind: "既有官方來源".into(),
            homepage: agency.homepage,
            status: "searchable".into(),
            adapter: "legacy".into(),
            slug: String::new(),
            feed: String::new(),
            news_page: String::new(),
            provenance: String::new(),
            reason: String::new(),
        })
        .collect::<Vec<_>>();
    entries.extend_from_slice(snapshot_entries());
    entries
}

pub fn searchable_agencies() -> Vec<Agency> {
    catalog_entries()
        .into_iter()
        .filter(|entry| {
            entry.status == "searchable"
                && matches!(
                    entry.adapter.as_str(),
                    "govuk_search" | "feed" | "html_news"
                )
        })
        .map(|entry| Agency {
            name_zh: if entry.name_zh.is_empty() {
                entry.name_en.clone()
            } else {
                entry.name_zh
            },
            name_en: entry.name_en,
            short_name: entry.id,
            homepage: entry.homepage.clone(),
            feeds: match entry.adapter.as_str() {
                "feed" => vec![entry.feed],
                "govuk_search" => vec![format!("{}.atom", entry.homepage)],
                _ => vec![],
            },
            news_pages: if entry.adapter == "html_news" {
                vec![entry.news_page]
            } else {
                vec![]
            },
            topics: vec![],
            link_include_patterns: if entry.adapter != "govuk_search" {
                vec![]
            } else {
                [
                    "/government/news/",
                    "/guidance/",
                    "/government/publications/",
                    "/government/consultations/",
                    "/government/research/",
                    "/government/statistics/",
                ]
                .into_iter()
                .map(Into::into)
                .collect()
            },
            official_pages: vec![],
        })
        .collect()
}

pub(crate) fn uses_govuk_search(identifier: &str) -> bool {
    identifier.starts_with("govuk:")
        && !snapshot_entries().iter().any(|entry| {
            entry.id == identifier && matches!(entry.adapter.as_str(), "feed" | "html_news")
        })
}

pub(crate) fn is_catalog_feed(identifier: &str) -> bool {
    snapshot_entries()
        .iter()
        .any(|entry| entry.id == identifier && entry.adapter == "feed")
}

pub(crate) fn is_catalog_html(identifier: &str) -> bool {
    snapshot_entries()
        .iter()
        .any(|entry| entry.id == identifier && entry.adapter == "html_news")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reviewed_adapter_controls_govuk_dispatch() {
        assert!(uses_govuk_search("govuk:unknown-test"));
        assert!(!uses_govuk_search("court-ew:judgments"));
        for entry in snapshot_entries() {
            if entry.status == "searchable"
                && matches!(entry.adapter.as_str(), "feed" | "html_news")
            {
                assert!(!uses_govuk_search(&entry.id));
                assert_eq!(is_catalog_feed(&entry.id), entry.adapter == "feed");
                assert_eq!(is_catalog_html(&entry.id), entry.adapter == "html_news");
            }
        }
    }
}
