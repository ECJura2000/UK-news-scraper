use anyhow::Result;
use async_trait::async_trait;
use futures::{stream, StreamExt};
use serde_json::Value;
use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
};

#[async_trait]
pub trait TranslationProvider: Send + Sync {
    async fn translate(&self, text: &str) -> Result<String>;
}
pub struct FreeGoogleProvider {
    client: reqwest::Client,
}
impl Default for FreeGoogleProvider {
    fn default() -> Self {
        Self {
            client: reqwest::Client::new(),
        }
    }
}
#[async_trait]
impl TranslationProvider for FreeGoogleProvider {
    async fn translate(&self, text: &str) -> Result<String> {
        let value: Value = self
            .client
            .get("https://translate.googleapis.com/translate_a/single")
            .query(&[
                ("client", "gtx"),
                ("sl", "en"),
                ("tl", "zh-TW"),
                ("dt", "t"),
                ("q", text),
            ])
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        let translated = value
            .get(0)
            .and_then(Value::as_array)
            .map(|parts| {
                parts
                    .iter()
                    .filter_map(|p| p.get(0).and_then(Value::as_str))
                    .collect::<String>()
            })
            .unwrap_or_default();
        if translated.is_empty() {
            anyhow::bail!("translation response is empty")
        }
        Ok(translated)
    }
}

pub struct TranslationService<P> {
    provider: P,
    cache_path: PathBuf,
    concurrency: usize,
}
impl<P: TranslationProvider> TranslationService<P> {
    pub fn new(provider: P, cache_path: PathBuf, concurrency: usize) -> Self {
        Self {
            provider,
            cache_path,
            concurrency,
        }
    }
    pub async fn translate_all(
        &self,
        texts: impl IntoIterator<Item = String>,
    ) -> (HashMap<String, String>, Vec<String>) {
        let mut cache = load_cache(&self.cache_path);
        let unique = texts
            .into_iter()
            .filter(|x| !x.is_empty())
            .collect::<std::collections::BTreeSet<_>>();
        let mut warnings = vec![];
        let pending = unique
            .into_iter()
            .filter(|text| !cache.contains_key(text))
            .collect::<Vec<_>>();
        let results = stream::iter(pending)
            .map(|text| async move {
                let result = self.provider.translate(&text).await;
                (text, result)
            })
            .buffer_unordered(self.concurrency.max(1))
            .collect::<Vec<_>>()
            .await;
        for (text, result) in results {
            match result {
                Ok(v) => {
                    cache.insert(text, v);
                }
                Err(e) => {
                    warnings.push(format!("翻譯失敗，保留英文：{e}"));
                    cache.insert(text.clone(), text);
                }
            }
        }
        if let Err(e) = save_cache(&self.cache_path, &cache) {
            warnings.push(format!("翻譯快取寫入失敗：{e}"))
        }
        (cache, warnings)
    }
}
fn load_cache(path: &Path) -> HashMap<String, String> {
    fs::read_to_string(path)
        .ok()
        .and_then(|x| serde_json::from_str(&x).ok())
        .unwrap_or_default()
}
fn save_cache(path: &Path, map: &HashMap<String, String>) -> Result<()> {
    if let Some(p) = path.parent() {
        fs::create_dir_all(p)?
    }
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, serde_json::to_vec_pretty(map)?)?;
    fs::rename(tmp, path)?;
    Ok(())
}
