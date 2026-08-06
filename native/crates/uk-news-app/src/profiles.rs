use anyhow::{Context, Result};
use chrono::Utc;
use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs,
    path::{Path, PathBuf},
};
use uk_news_core::{
    FilterProfile, KeywordDefinition, KeywordStrength, ProfileTopic, PROFILE_SCHEMA_VERSION,
};

const SUPPORTING: [&str; 7] = [
    "copyright",
    "evaluation",
    "innovation",
    "platform",
    "resilience",
    "supply chain",
    "technology",
];
const TOPICS: [(&str, &[&str]); 6] = [
    (
        "Science & Technology",
        &[
            "science",
            "scientific",
            "science and technology",
            "sci tech",
            "technology",
            "technological",
            "innovation",
            "research and development",
            "R&D",
        ],
    ),
    (
        "AI",
        &[
            "artificial intelligence",
            "AI",
            "machine learning",
            "foundation model",
            "foundation models",
            "frontier model",
            "frontier AI",
            "generative AI",
            "automated decision",
            "automated decision-making",
            "algorithm",
            "algorithmic accountability",
            "explainability",
            "fairness",
            "AI Safety Institute",
            "AI Security Institute",
            "model evaluation",
            "evaluation",
            "copyright",
            "text and data mining",
            "TDM",
            "privacy-by-design",
            "AI and data protection",
        ],
    ),
    (
        "資料治理/隱私/數位身份",
        &[
            "data protection",
            "UK GDPR",
            "GDPR",
            "Data Protection Act",
            "international data transfer",
            "adequacy",
            "standard contractual clauses",
            "data use",
            "data access",
            "open data",
            "data reuse",
            "data reuse policy",
            "Open Government Data Framework",
            "digital identity",
            "trust framework",
            "GOV.UK One Login",
            "One Login",
            "UK Digital Identity and Attributes Trust Framework",
        ],
    ),
    (
        "數位平台",
        &[
            "online safety",
            "Online Safety Act",
            "platform",
            "illegal content",
            "child safety",
            "recommendation algorithm",
            "algorithm transparency",
            "media plurality",
            "broadcast impartiality",
            "online influence transparency",
            "disinformation",
            "misinformation",
            "foreign information manipulation",
            "electoral information manipulation",
            "digital markets",
            "Digital Markets Competition and Consumers Act",
            "Strategic Market Status",
            "SMS",
            "systemic risk",
        ],
    ),
    (
        "網路安全/資安",
        &[
            "cyber",
            "cybersecurity",
            "network and information systems",
            "NIS",
            "critical infrastructure",
            "critical national infrastructure",
            "product security",
            "telecommunications infrastructure",
            "vulnerability",
            "coordinated vulnerability disclosure",
            "secure by design",
            "secure-by-design",
            "SBOM",
            "software bill of materials",
            "supply chain",
            "government cyber security strategy",
            "Cyber Essentials",
            "incident response",
            "resilience",
            "protective security",
            "hybrid threat",
            "hybrid threat resilience",
            "critical infrastructure protection",
            "national cyber resilience",
        ],
    ),
    (
        "半導體/量子技術",
        &[
            "semiconductor",
            "National Semiconductor Strategy",
            "semiconductor strategy",
            "chip",
            "microelectronics",
            "export control",
            "quantum",
            "National Quantum Strategy",
            "quantum technologies",
            "quantum computing",
            "quantum R&D",
        ],
    ),
];

pub fn default_profile() -> FilterProfile {
    FilterProfile {
        profile_id: "uk-tech-law".into(),
        name: "UK 科技法制".into(),
        description: "英國科技、AI、資料治理、平台、資安、半導體與量子政策觀測".into(),
        version: PROFILE_SCHEMA_VERSION,
        selected_sources: [
            "DSIT",
            "AISI",
            "ICO",
            "CMA",
            "UK IPO",
            "GDS",
            "Ofcom",
            "NCSC",
            "Electoral Commission",
            "Cabinet Office",
            "NPSA",
            "DBT",
            "UKRI",
            "UK Parliament",
        ]
        .into_iter()
        .map(Into::into)
        .collect(),
        topics: TOPICS
            .iter()
            .map(|(name, words)| ProfileTopic {
                name: (*name).into(),
                keywords: words
                    .iter()
                    .map(|word| KeywordDefinition {
                        phrase: (*word).into(),
                        strength: if SUPPORTING.iter().any(|x| x.eq_ignore_ascii_case(word)) {
                            KeywordStrength::Supporting
                        } else if word.trim().contains(' ') || word.trim().len() >= 10 {
                            KeywordStrength::Core
                        } else {
                            KeywordStrength::General
                        },
                    })
                    .collect(),
            })
            .collect(),
        minimum_score: 3,
    }
}

pub fn load_profile(value: Option<&str>) -> Result<FilterProfile> {
    let Some(value) = value else {
        return Ok(default_profile());
    };
    let path = Path::new(value);
    if path.exists() {
        let p: FilterProfile =
            serde_json::from_str(&fs::read_to_string(path)?).context("parse profile JSON")?;
        validate_profile(&p)?;
        Ok(p)
    } else {
        load_profiles()?
            .into_iter()
            .find(|p| p.profile_id == value)
            .with_context(|| format!("找不到設定檔：{value}"))
    }
}
pub fn validate_profile(p: &FilterProfile) -> Result<()> {
    if p.version != PROFILE_SCHEMA_VERSION {
        anyhow::bail!("不支援的設定檔版本：{}", p.version)
    }
    if !Regex::new(r"^[a-z0-9][a-z0-9-]{1,48}$")
        .unwrap()
        .is_match(&p.profile_id)
        || p.selected_sources.is_empty()
        || p.topics.is_empty()
        || p.minimum_score < 1
    {
        anyhow::bail!("設定檔欄位不完整")
    }
    let available = uk_news_sources::agencies()
        .into_iter()
        .map(|a| a.short_name)
        .chain(["UK Parliament".into()])
        .collect::<HashSet<_>>();
    if let Some(source) = p.selected_sources.iter().find(|x| !available.contains(*x)) {
        anyhow::bail!("設定檔包含未知來源：{source}")
    }
    let mut keywords = HashSet::new();
    for topic in &p.topics {
        if topic.name.trim().is_empty() || topic.keywords.is_empty() {
            anyhow::bail!("主題或關鍵詞不可空白")
        }
        for word in &topic.keywords {
            if word.phrase.trim().is_empty() || !keywords.insert(word.phrase.to_lowercase()) {
                anyhow::bail!("關鍵詞空白或重複：{}", word.phrase)
            }
        }
    }
    Ok(())
}

#[derive(Serialize, Deserialize)]
struct ProfileCollection {
    schema_version: u32,
    profiles: Vec<FilterProfile>,
}
#[derive(Debug, Serialize)]
pub struct ProfileLoadReport {
    pub profiles: Vec<FilterProfile>,
    pub warning: String,
    pub recovery_path: Option<PathBuf>,
}
pub fn profiles_path() -> PathBuf {
    #[cfg(target_os = "macos")]
    let root = home().join("Library/Application Support");
    #[cfg(target_os = "windows")]
    let root = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join("AppData/Roaming"));
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let root = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".config"));
    root.join("UKNewsScraper/profiles.json")
}
fn home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}
pub fn load_profiles() -> Result<Vec<FilterProfile>> {
    load_profiles_from(&profiles_path())
}
fn load_profiles_from(path: &Path) -> Result<Vec<FilterProfile>> {
    let mut profiles = vec![default_profile()];
    if !path.exists() {
        return Ok(profiles);
    }
    let raw: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(path)?).context("無法讀取設定檔")?;
    let payload: ProfileCollection =
        serde_json::from_value(migrate_collection(raw)?).context("設定檔集合格式錯誤")?;
    if payload.schema_version > PROFILE_SCHEMA_VERSION {
        anyhow::bail!("不支援的設定檔集合版本：{}", payload.schema_version)
    }
    for p in payload.profiles {
        validate_profile(&p)?;
        if profiles.iter().any(|x| x.profile_id == p.profile_id) {
            anyhow::bail!("設定檔 ID 重複：{}", p.profile_id)
        }
        profiles.push(p)
    }
    Ok(profiles)
}
pub fn load_profiles_with_recovery() -> ProfileLoadReport {
    let path = profiles_path();
    match load_profiles_from(&path) {
        Ok(profiles) => ProfileLoadReport {
            profiles,
            warning: String::new(),
            recovery_path: None,
        },
        Err(error) => {
            let recovery_path = quarantine(&path).ok().flatten();
            let location = recovery_path
                .as_ref()
                .map(|value| format!("，原檔保留於 {}", value.display()))
                .unwrap_or_default();
            ProfileLoadReport {
                profiles: vec![default_profile()],
                warning: format!("{error:#}；已載入內建設定{location}"),
                recovery_path,
            }
        }
    }
}
fn migrate_collection(mut raw: serde_json::Value) -> Result<serde_json::Value> {
    let object = raw
        .as_object_mut()
        .context("設定檔集合必須是 JSON object")?;
    let version = object
        .get("schema_version")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or(0);
    if version > PROFILE_SCHEMA_VERSION as u64 {
        anyhow::bail!("不支援的設定檔集合版本：{version}")
    }
    let profiles = object
        .get_mut("profiles")
        .and_then(serde_json::Value::as_array_mut)
        .context("設定檔集合必須包含 profiles array")?;
    if version == 0 {
        for profile in profiles {
            let profile = profile
                .as_object_mut()
                .context("設定檔必須是 JSON object")?;
            let profile_version = profile
                .get("version")
                .and_then(serde_json::Value::as_u64)
                .unwrap_or(0);
            if profile_version > PROFILE_SCHEMA_VERSION as u64 {
                anyhow::bail!("不支援的設定檔版本：{profile_version}")
            }
            if profile_version == 0 {
                if let Some(topics) = profile
                    .get_mut("topics")
                    .and_then(serde_json::Value::as_array_mut)
                {
                    for topic in topics {
                        if let Some(keywords) = topic
                            .get_mut("keywords")
                            .and_then(serde_json::Value::as_array_mut)
                        {
                            for keyword in keywords.iter_mut() {
                                if let Some(phrase) = keyword.as_str() {
                                    *keyword = serde_json::json!({
                                        "phrase": phrase,
                                        "strength": "general"
                                    });
                                }
                            }
                        }
                    }
                }
                profile.insert("version".into(), serde_json::json!(PROFILE_SCHEMA_VERSION));
                profile
                    .entry("description")
                    .or_insert_with(|| serde_json::json!(""));
                profile
                    .entry("minimum_score")
                    .or_insert_with(|| serde_json::json!(3));
            }
        }
        object.insert(
            "schema_version".into(),
            serde_json::json!(PROFILE_SCHEMA_VERSION),
        );
    }
    Ok(raw)
}
fn quarantine(path: &Path) -> Result<Option<PathBuf>> {
    if !path.exists() {
        return Ok(None);
    }
    let stamp = Utc::now().format("%Y%m%dT%H%M%SZ");
    let recovery = path.with_file_name(format!(
        "{}.corrupt-{stamp}.json",
        path.file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("profiles")
    ));
    fs::rename(path, &recovery)?;
    Ok(Some(recovery))
}
pub fn save_profile(profile: FilterProfile) -> Result<PathBuf> {
    validate_profile(&profile)?;
    if profile.profile_id == "uk-tech-law" {
        anyhow::bail!("內建設定檔不可覆寫")
    }
    let path = profiles_path();
    let mut profiles = load_profiles().unwrap_or_else(|_| vec![default_profile()]);
    profiles.retain(|p| p.profile_id != "uk-tech-law" && p.profile_id != profile.profile_id);
    profiles.push(profile);
    write_profiles(&path, &profiles)?;
    Ok(path)
}
pub fn delete_profile(id: &str) -> Result<bool> {
    if id == "uk-tech-law" {
        return Ok(false);
    }
    let path = profiles_path();
    let mut profiles = load_profiles()?;
    let before = profiles.len();
    profiles.retain(|p| p.profile_id == "uk-tech-law" || p.profile_id != id);
    if profiles.len() == before {
        return Ok(false);
    }
    write_profiles(
        &path,
        &profiles
            .into_iter()
            .filter(|p| p.profile_id != "uk-tech-law")
            .collect::<Vec<_>>(),
    )?;
    Ok(true)
}
fn write_profiles(path: &Path, profiles: &[FilterProfile]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?
    }
    if path.exists() {
        let backup = path.with_extension("json.bak");
        let tmp_backup = path.with_extension("json.bak.tmp");
        fs::copy(path, &tmp_backup)?;
        fs::rename(tmp_backup, backup)?
    }
    let tmp = path.with_extension("json.tmp");
    fs::write(
        &tmp,
        format!(
            "{}\n",
            serde_json::to_string_pretty(&ProfileCollection {
                schema_version: PROFILE_SCHEMA_VERSION,
                profiles: profiles.to_vec()
            })?
        ),
    )?;
    fs::rename(tmp, path)?;
    Ok(())
}
pub fn profile_hash(p: &FilterProfile) -> String {
    let value = serde_json::to_value(p).unwrap();
    let canonical = canonical_json(&value);
    format!("{:x}", Sha256::digest(canonical.as_bytes()))
}
fn canonical_json(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::Object(m) => {
            let mut keys = m.keys().collect::<Vec<_>>();
            keys.sort();
            format!(
                "{{{}}}",
                keys.into_iter()
                    .map(|k| format!(
                        "{}:{}",
                        serde_json::to_string(k).unwrap(),
                        canonical_json(&m[k])
                    ))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        serde_json::Value::Array(a) => format!(
            "[{}]",
            a.iter().map(canonical_json).collect::<Vec<_>>().join(",")
        ),
        _ => serde_json::to_string(v).unwrap(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn default_profile_hash_matches_python_contract() {
        assert_eq!(
            profile_hash(&default_profile()),
            "4155af3e893e9fdf2ccab4361e87548321ce62a2a7032de7ebb121c5bd72c915"
        );
    }

    #[test]
    fn migrates_python_v0_profile_collection() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.json");
        fs::write(&path, r#"{"profiles":[{"profile_id":"old-profile","name":"Old","selected_sources":["NCSC"],"topics":[{"name":"Cyber","keywords":["cyber"]}]}]}"#).unwrap();
        let profiles = load_profiles_from(&path).unwrap();
        assert_eq!(profiles[1].version, 1);
        assert_eq!(
            profiles[1].topics[0].keywords[0].strength,
            KeywordStrength::General
        );
    }
}
