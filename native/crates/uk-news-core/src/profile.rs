use serde::{Deserialize, Serialize};

pub const PROFILE_SCHEMA_VERSION: u32 = 1;
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
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProfileTopic {
    pub name: String,
    pub keywords: Vec<KeywordDefinition>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FilterProfile {
    pub profile_id: String,
    pub name: String,
    pub description: String,
    pub version: u32,
    pub selected_sources: Vec<String>,
    pub topics: Vec<ProfileTopic>,
    pub minimum_score: i32,
}
