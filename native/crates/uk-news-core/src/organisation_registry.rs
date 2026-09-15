use crate::Agency;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};

const BUILTINS: &[(&str, &str)] = &[
    (
        "aisi.json",
        include_str!("../../../../organisation_registry/aisi.json"),
    ),
    (
        "bist.json",
        include_str!("../../../../organisation_registry/bist.json"),
    ),
    (
        "cabinet-office.json",
        include_str!("../../../../organisation_registry/cabinet-office.json"),
    ),
    (
        "cma.json",
        include_str!("../../../../organisation_registry/cma.json"),
    ),
    (
        "dcms.json",
        include_str!("../../../../organisation_registry/dcms.json"),
    ),
    (
        "dsit-transition.json",
        include_str!("../../../../organisation_registry/dsit-transition.json"),
    ),
    (
        "electoral-commission.json",
        include_str!("../../../../organisation_registry/electoral-commission.json"),
    ),
    (
        "gds.json",
        include_str!("../../../../organisation_registry/gds.json"),
    ),
    (
        "ico.json",
        include_str!("../../../../organisation_registry/ico.json"),
    ),
    (
        "ncsc.json",
        include_str!("../../../../organisation_registry/ncsc.json"),
    ),
    (
        "npsa.json",
        include_str!("../../../../organisation_registry/npsa.json"),
    ),
    (
        "ofcom.json",
        include_str!("../../../../organisation_registry/ofcom.json"),
    ),
    (
        "uk-ipo.json",
        include_str!("../../../../organisation_registry/uk-ipo.json"),
    ),
    (
        "ukri.json",
        include_str!("../../../../organisation_registry/ukri.json"),
    ),
];
pub const ORGANISATION_TEMPLATE: &str =
    include_str!("../../../../organisation_registry/organisation.example.json");
const TOPICS: &[&str] = &[
    "Science & Technology",
    "AI",
    "資料治理/隱私/數位身份",
    "數位平台",
    "網路安全/資安",
    "半導體/量子技術",
];
const ADAPTERS: &[&str] = &[
    "govuk_atom",
    "generic_rss",
    "html_index",
    "electoral_sitemap",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationNames {
    pub zh: String,
    pub en: String,
    pub short: String,
    #[serde(default)]
    pub publisher_aliases: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationSources {
    pub homepage: String,
    pub feeds: Vec<String>,
    pub news_pages: Vec<String>,
    pub official_pages: Vec<String>,
    pub adapter: String,
    #[serde(default)]
    pub fallbacks: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationFilter {
    pub topics: Vec<String>,
    pub include_path_patterns: Vec<String>,
    #[serde(default)]
    pub exclude_title_patterns: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationHealth {
    pub critical: bool,
    pub minimum_items: usize,
    pub maximum_age_days: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationHistory {
    pub effective_from: String,
    #[serde(default)]
    pub predecessors: Vec<String>,
    #[serde(default)]
    pub successors: Vec<String>,
    #[serde(default)]
    pub transitional_sources: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationModule {
    pub schema_version: u32,
    pub module_version: String,
    pub canonical_id: String,
    pub names: OrganisationNames,
    pub sources: OrganisationSources,
    pub filter: OrganisationFilter,
    pub health: OrganisationHealth,
    pub history: OrganisationHistory,
    #[serde(default)]
    pub responsibility_by_topic: BTreeMap<String, String>,
    #[serde(skip)]
    pub source_path: String,
    #[serde(skip)]
    pub external: bool,
    #[serde(skip)]
    pub payload: Value,
}

impl OrganisationModule {
    pub fn agency(&self) -> Agency {
        Agency {
            name_zh: self.names.zh.clone(),
            name_en: self.names.en.clone(),
            short_name: self.names.short.clone(),
            homepage: self.sources.homepage.clone(),
            feeds: self.sources.feeds.clone(),
            news_pages: self.sources.news_pages.clone(),
            topics: self.filter.topics.clone(),
            link_include_patterns: self.filter.include_path_patterns.clone(),
            official_pages: self.sources.official_pages.clone(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganisationModuleSummary {
    pub canonical_id: String,
    pub module_version: String,
    pub source: String,
    pub external: bool,
}
#[derive(Debug, Clone)]
pub struct OrganisationRegistry {
    pub modules: Vec<OrganisationModule>,
    pub errors: Vec<String>,
    pub registry_hash: String,
}

impl OrganisationRegistry {
    pub fn agencies(&self) -> Vec<Agency> {
        self.modules
            .iter()
            .map(OrganisationModule::agency)
            .collect()
    }
    pub fn module_summaries(&self) -> Vec<OrganisationModuleSummary> {
        self.modules
            .iter()
            .map(|m| OrganisationModuleSummary {
                canonical_id: m.canonical_id.clone(),
                module_version: m.module_version.clone(),
                source: m.source_path.clone(),
                external: m.external,
            })
            .collect()
    }
    pub fn topics_by_source(&self) -> BTreeMap<String, BTreeSet<String>> {
        self.modules
            .iter()
            .map(|m| {
                (
                    m.canonical_id.clone(),
                    m.filter.topics.iter().cloned().collect(),
                )
            })
            .collect()
    }
}

pub fn external_registry_dir() -> PathBuf {
    if let Ok(path) = env::var("UK_NEWS_ORGANISATION_DIR") {
        return PathBuf::from(path);
    }
    #[cfg(target_os = "macos")]
    return PathBuf::from(env::var_os("HOME").unwrap_or_default())
        .join("Library/Application Support/UKNewsScraper/organisations.d");
    #[cfg(target_os = "windows")]
    return PathBuf::from(env::var_os("APPDATA").unwrap_or_default())
        .join("UKNewsScraper/organisations.d");
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    return PathBuf::from(
        env::var_os("XDG_CONFIG_HOME").unwrap_or_else(|| env::var_os("HOME").unwrap_or_default()),
    )
    .join("UKNewsScraper/organisations.d");
}

pub fn load_organisation_registry() -> OrganisationRegistry {
    load_organisation_registry_from(&external_registry_dir())
}
pub fn load_organisation_registry_from(external_dir: &Path) -> OrganisationRegistry {
    let mut builtins = BTreeMap::new();
    for (name, text) in BUILTINS {
        let module = parse(text, &format!("builtin:{name}"), false)
            .expect("invalid built-in organisation JSON");
        builtins.insert(module.canonical_id.clone(), module);
    }
    let mut active = builtins.clone();
    let mut errors = vec![];
    let mut external_ids = BTreeSet::new();
    if let Ok(entries) = fs::read_dir(external_dir) {
        let mut paths = entries
            .flatten()
            .map(|e| e.path())
            .filter(|p| {
                p.extension().is_some_and(|v| v == "json")
                    && p.file_name()
                        .is_none_or(|v| v != "organisation.example.json")
            })
            .collect::<Vec<_>>();
        paths.sort();
        for path in paths {
            match fs::read_to_string(&path)
                .map_err(|e| e.to_string())
                .and_then(|text| parse(&text, &path.display().to_string(), true))
            {
                Ok(module) => {
                    if !external_ids.insert(module.canonical_id.clone()) {
                        errors.push(format!(
                            "{}:canonical_id 重複：{}",
                            path.display(),
                            module.canonical_id
                        ));
                        continue;
                    }
                    active.insert(module.canonical_id.clone(), module);
                }
                Err(error) => errors.push(format!("{}:{error}", path.display())),
            }
        }
    }
    let ids = active.keys().cloned().collect::<BTreeSet<_>>();
    let invalid = active
        .values()
        .filter(|m| {
            m.history
                .successors
                .iter()
                .chain(m.responsibility_by_topic.values())
                .any(|id| !ids.contains(id))
        })
        .map(|m| m.canonical_id.clone())
        .collect::<Vec<_>>();
    for id in invalid {
        let module = active.get(&id).expect("active module");
        errors.push(format!("{}:未知機關引用", module.source_path));
        if module.external {
            if let Some(builtin) = builtins.get(&id) {
                active.insert(id, builtin.clone());
            } else {
                active.remove(&id);
            }
        }
    }
    let mut modules = active.into_values().collect::<Vec<_>>();
    modules.sort_by(|left, right| {
        left.canonical_id
            .to_lowercase()
            .cmp(&right.canonical_id.to_lowercase())
    });
    let values = modules
        .iter()
        .map(|m| canonicalize(&m.payload))
        .collect::<Vec<Value>>();
    let registry_hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&values).expect("serializable registry"))
    );
    OrganisationRegistry {
        modules,
        errors,
        registry_hash,
    }
}

fn parse(text: &str, source_path: &str, external: bool) -> Result<OrganisationModule, String> {
    let payload: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let mut module: OrganisationModule =
        serde_json::from_value(payload.clone()).map_err(|e| e.to_string())?;
    if module.schema_version != 1 {
        return Err(format!(
            "不支援的 schema_version：{}",
            module.schema_version
        ));
    }
    if !ADAPTERS.contains(&module.sources.adapter.as_str()) {
        return Err(format!("未知 adapter：{}", module.sources.adapter));
    }
    if module.sources.fallbacks.iter().any(|v| v != "google_news") {
        return Err("未知 fallback".into());
    }
    if module.filter.topics.is_empty()
        || module
            .filter
            .topics
            .iter()
            .any(|t| !TOPICS.contains(&t.as_str()))
    {
        return Err("未知或空白主題".into());
    }
    if module
        .sources
        .homepage
        .parse::<url::Url>()
        .ok()
        .is_none_or(|url| url.scheme() != "https")
    {
        return Err("homepage 必須使用 https".into());
    }
    module.source_path = source_path.into();
    module.external = external;
    module.payload = payload;
    Ok(module)
}

fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Object(values) => {
            let sorted = values
                .iter()
                .map(|(key, value)| (key.clone(), canonicalize(value)))
                .collect::<BTreeMap<_, _>>();
            Value::Object(sorted.into_iter().collect())
        }
        Value::Array(values) => Value::Array(values.iter().map(canonicalize).collect()),
        other => other.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shared_registry_matches_python_hash() {
        let r = load_organisation_registry_from(Path::new("/path/that/does/not/exist"));
        assert_eq!(r.modules.len(), 14);
        assert_eq!(
            r.registry_hash,
            "2dcf8d0cd36317eebef6e47c51a64c2372ceed3a7675e6d8daab5332a662308a"
        );
    }
    #[test]
    fn template_is_valid_module() {
        assert!(parse(ORGANISATION_TEMPLATE, "template", true).is_ok());
    }
}
