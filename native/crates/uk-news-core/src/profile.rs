use serde::{Deserialize, Serialize};

pub const PROFILE_SCHEMA_VERSION: u32 = 2;
pub const DEFAULT_PROFILE_ID: &str = "uk-tech-law";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum KeywordStrength {
    Core,
    General,
    Supporting,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct KeywordDefinition {
    pub phrase: String,
    pub strength: KeywordStrength,
    #[serde(default)]
    pub synonyms: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProfileTopic {
    pub name: String,
    pub keywords: Vec<KeywordDefinition>,
    #[serde(default)]
    pub minimum_bm25_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FilterProfile {
    pub profile_id: String,
    pub name: String,
    pub description: String,
    pub version: u32,
    pub selected_sources: Vec<String>,
    pub topics: Vec<ProfileTopic>,
    pub minimum_score: i32,
    #[serde(default = "default_ranking_method")]
    pub ranking_method: String,
    #[serde(default = "default_k1")]
    pub bm25_k1: f64,
    #[serde(default = "default_b")]
    pub bm25_b: f64,
    #[serde(default = "default_title_weight")]
    pub title_weight: f64,
}

fn default_ranking_method() -> String {
    "weighted_keywords".into()
}
fn default_k1() -> f64 {
    1.2
}
fn default_b() -> f64 {
    0.75
}
fn default_title_weight() -> f64 {
    2.0
}
