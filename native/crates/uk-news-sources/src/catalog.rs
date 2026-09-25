use serde::{Deserialize, Serialize};
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
    pub provenance: String,
    pub reason: String,
}

#[derive(Deserialize)]
struct Snapshot {
    schema_version: u32,
    sources: Vec<CatalogEntry>,
}

pub fn catalog_entries() -> Vec<CatalogEntry> {
    let snapshot: Snapshot = serde_json::from_str(include_str!(
        "../../../../UK_news_scraper/data/source_catalog.json"
    ))
    .expect("valid official source catalog");
    assert_eq!(snapshot.schema_version, 1);
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
            provenance: String::new(),
            reason: String::new(),
        })
        .collect::<Vec<_>>();
    entries.extend(snapshot.sources);
    entries
}

pub fn searchable_agencies() -> Vec<Agency> {
    catalog_entries()
        .into_iter()
        .filter(|entry| {
            entry.status == "searchable"
                && matches!(entry.adapter.as_str(), "govuk_search" | "feed")
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
            feeds: vec![if entry.adapter == "feed" {
                entry.feed
            } else {
                format!("{}.atom", entry.homepage)
            }],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: if entry.adapter == "feed" {
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
