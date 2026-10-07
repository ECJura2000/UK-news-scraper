//! Additive diagnostics, deliberately excluded from fingerprints.
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct HttpCounts {
    pub attempted_count: usize,
    pub retry_count: usize,
    pub rate_limited_count: usize,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PipelineCounts {
    pub list_items_count: Option<usize>,
    pub candidate_count: usize,
    pub source_output_count: usize,
    pub date_filtered_count: usize,
    pub deduped_count: usize,
    pub final_output_count: usize,
    pub relevant_output_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct RunPerformance {
    pub schema_version: u32,
    pub runtime: String,
    pub runtime_version: String,
    pub workers: usize,
    pub translation_cache_hits: usize,
    pub translation_cache_misses: usize,
    pub run_kind: String,
    pub total_wall_seconds: f64,
    pub total_endpoint: String,
    pub detail_fetch_enabled: bool,
    pub stages: BTreeMap<String, Option<f64>>,
    pub counts: BTreeMap<String, PipelineCounts>,
    pub http: BTreeMap<String, HttpCounts>,
}

impl Default for RunPerformance {
    fn default() -> Self {
        Self {
            schema_version: 1,
            runtime: "rust".into(),
            runtime_version: String::new(),
            workers: 0,
            translation_cache_hits: 0,
            translation_cache_misses: 0,
            run_kind: "full".into(),
            total_wall_seconds: 0.0,
            total_endpoint: "before_summary_serialization".into(),
            detail_fetch_enabled: false,
            stages: [
                "collection_wall_seconds",
                "dedupe_work_seconds",
                "relevance_seconds",
                "translation_seconds",
                "excel_write_seconds",
                "json_write_seconds",
            ]
            .into_iter()
            .map(|name| (name.into(), Some(0.0)))
            .collect(),
            counts: BTreeMap::new(),
            http: ["list", "search_api", "fallback", "translation"]
                .into_iter()
                .map(|name| (name.into(), HttpCounts::default()))
                .collect(),
        }
    }
}
