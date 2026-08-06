use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RunStatus {
    Complete,
    Degraded,
}

impl std::fmt::Display for RunStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Complete => "complete",
            Self::Degraded => "degraded",
        })
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ContentType {
    #[default]
    News,
    Guidance,
    Report,
    Publication,
}

impl std::fmt::Display for ContentType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::News => "news",
            Self::Guidance => "guidance",
            Self::Report => "report",
            Self::Publication => "publication",
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Agency {
    pub name_zh: String,
    pub name_en: String,
    pub short_name: String,
    pub homepage: String,
    #[serde(default)]
    pub feeds: Vec<String>,
    #[serde(default)]
    pub news_pages: Vec<String>,
    #[serde(default)]
    pub topics: Vec<String>,
    #[serde(default)]
    pub link_include_patterns: Vec<String>,
    #[serde(default)]
    pub official_pages: Vec<String>,
}

impl Agency {
    pub fn display_name(&self) -> String {
        format!("{} ({})", self.name_zh, self.short_name)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NewsItem {
    pub agency: String,
    pub agency_en: String,
    pub unit_category: Option<String>,
    pub title: String,
    pub link: String,
    pub published_at: DateTime<Utc>,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub source_feed: String,
    #[serde(default)]
    pub matched_topics: Vec<String>,
    #[serde(default)]
    pub matched_keywords: Vec<String>,
    #[serde(default)]
    pub title_matched_keywords: Vec<String>,
    #[serde(default)]
    pub summary_matched_keywords: Vec<String>,
    #[serde(default)]
    pub core_matched_keywords: Vec<String>,
    #[serde(default)]
    pub general_matched_keywords: Vec<String>,
    #[serde(default)]
    pub supporting_matched_keywords: Vec<String>,
    #[serde(default)]
    pub title_keyword_strengths: BTreeMap<String, String>,
    #[serde(default)]
    pub summary_keyword_strengths: BTreeMap<String, String>,
    #[serde(default)]
    pub relevance_score: i32,
    #[serde(default)]
    pub relevance_level: String,
    #[serde(default)]
    pub content_type: ContentType,
}

impl NewsItem {
    pub fn date_text(&self) -> String {
        self.published_at.date_naive().to_string()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ParliamentBriefing {
    pub published_at: DateTime<Utc>,
    pub chamber: String,
    pub publisher: String,
    pub title: String,
    pub summary: String,
    pub identifier: String,
    pub webpage_url: String,
    #[serde(default)]
    pub pdf_url: String,
    #[serde(default)]
    pub topics: Vec<String>,
    #[serde(default = "default_document_type")]
    pub document_type: String,
    #[serde(default)]
    pub fetched_from: String,
    #[serde(default)]
    pub matched_topics: Vec<String>,
    #[serde(default)]
    pub matched_keywords: Vec<String>,
    #[serde(default)]
    pub title_matched_keywords: Vec<String>,
    #[serde(default)]
    pub summary_matched_keywords: Vec<String>,
    #[serde(default)]
    pub core_matched_keywords: Vec<String>,
    #[serde(default)]
    pub general_matched_keywords: Vec<String>,
    #[serde(default)]
    pub supporting_matched_keywords: Vec<String>,
    #[serde(default)]
    pub relevance_score: i32,
    #[serde(default)]
    pub relevance_level: String,
}

fn default_document_type() -> String {
    "Research Briefing".into()
}
impl ParliamentBriefing {
    pub fn date_text(&self) -> String {
        self.published_at.date_naive().to_string()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SourceHealth {
    pub source: String,
    pub critical: bool,
    pub success: bool,
    pub item_count: usize,
    pub duration_seconds: f64,
    #[serde(default)]
    pub newest_published_at: String,
    #[serde(default)]
    pub warning: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunSummary {
    pub run_id: String,
    pub generated_at: String,
    pub period_start: String,
    pub period_end: String,
    pub output_file: String,
    pub all_news_count: usize,
    pub filtered_news_count: usize,
    pub parliament_count: usize,
    pub filtered_parliament_count: usize,
    pub status: RunStatus,
    pub warnings: Vec<String>,
    pub data_fingerprint: String,
    pub delivery_id: String,
    pub source_health: Vec<SourceHealth>,
    #[serde(default = "default_profile_id")]
    pub profile_id: String,
    #[serde(default = "default_profile_name")]
    pub profile_name: String,
    #[serde(default = "default_profile_version")]
    pub profile_version: u32,
    #[serde(default)]
    pub profile_hash: String,
    #[serde(default)]
    pub selected_sources: Vec<String>,
    #[serde(default = "default_minimum_score")]
    pub minimum_score: i32,
    #[serde(default = "default_calendar")]
    pub excel_date_calendar: String,
}

fn default_profile_id() -> String {
    "uk-tech-law".into()
}
fn default_profile_name() -> String {
    "UK 科技法制".into()
}
fn default_profile_version() -> u32 {
    1
}
fn default_minimum_score() -> i32 {
    3
}
fn default_calendar() -> String {
    "gregorian".into()
}
