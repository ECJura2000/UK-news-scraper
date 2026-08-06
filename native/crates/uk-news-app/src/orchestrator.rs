use crate::{default_profile, profile_hash, FreeGoogleProvider, TranslationService};
use anyhow::{Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashSet,
    fs,
    path::{Path, PathBuf},
};
use uk_news_core::{
    assess_news, assess_parliament, make_data_fingerprint, make_delivery_id, FilterProfile,
    NewsItem, ParliamentBriefing, RunStatus, RunSummary,
};
use uk_news_export::{export_news, CalendarMode, ExportOptions};
use uk_news_sources::{fetch_agencies, fetch_parliament, FetchResult};

pub struct RunOptions {
    pub since: NaiveDate,
    pub until: NaiveDate,
    pub output: PathBuf,
    pub workers: usize,
    pub profile: FilterProfile,
    pub calendar: CalendarMode,
    pub translation_cache: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunData {
    pub news: Vec<NewsItem>,
    pub parliament: Vec<ParliamentBriefing>,
}

pub async fn execute(options: RunOptions) -> Result<(PathBuf, PathBuf, RunSummary)> {
    let (since, until) = utc_range(options.since, options.until);
    let selected = options.profile.selected_sources.clone();
    let agencies = fetch_agencies(since, until, options.workers, &selected).await;
    let parliament = if selected.iter().any(|x| x == "UK Parliament") {
        fetch_parliament(since, until).await
    } else {
        FetchResult {
            items: vec![],
            health: vec![],
            warnings: vec![],
        }
    };
    finalize(options, agencies, parliament).await
}

pub async fn retry_failed_sources(
    options: RunOptions,
    previous_summary_path: &Path,
) -> Result<(PathBuf, PathBuf, RunSummary)> {
    let previous: RunSummary = serde_json::from_str(
        &fs::read_to_string(previous_summary_path)
            .with_context(|| format!("讀取執行摘要：{}", previous_summary_path.display()))?,
    )?;
    if !previous.profile_hash.is_empty() && previous.profile_hash != profile_hash(&options.profile)
    {
        anyhow::bail!(
            "重試必須使用原執行設定檔：{} ({})",
            previous.profile_name,
            previous.profile_id
        )
    }
    let previous_data_path = data_path_for_summary(previous_summary_path);
    let previous_data: RunData = serde_json::from_str(
        &fs::read_to_string(&previous_data_path)
            .with_context(|| format!("找不到重試資料：{}", previous_data_path.display()))?,
    )?;
    let agency_names = uk_news_sources::agencies()
        .into_iter()
        .map(|agency| agency.short_name)
        .collect::<HashSet<_>>();
    let failed_agencies = previous
        .source_health
        .iter()
        .filter(|health| !health.success || !health.warning.is_empty())
        .filter(|health| agency_names.contains(&health.source))
        .map(|health| health.source.clone())
        .collect::<Vec<_>>();
    let retry_parliament = previous.source_health.iter().any(|health| {
        (!health.success || !health.warning.is_empty())
            && (health.source.contains("Parliament")
                || health.source.contains("Commons")
                || health.source.contains("Lords")
                || health.source.contains("POST"))
    });
    if failed_agencies.is_empty() && !retry_parliament {
        anyhow::bail!("上次執行沒有需要重試的異常來源")
    }

    let (since, until) = utc_range(options.since, options.until);
    let retried_agencies = if failed_agencies.is_empty() {
        FetchResult {
            items: vec![],
            health: vec![],
            warnings: vec![],
        }
    } else {
        fetch_agencies(since, until, options.workers, &failed_agencies).await
    };
    let retried_parliament = if retry_parliament {
        fetch_parliament(since, until).await
    } else {
        FetchResult {
            items: previous_data.parliament,
            health: previous
                .source_health
                .iter()
                .filter(|health| is_parliament_health(&health.source))
                .cloned()
                .collect(),
            warnings: vec![],
        }
    };

    let failed_set = failed_agencies.iter().collect::<HashSet<_>>();
    let mut news = previous_data
        .news
        .into_iter()
        .filter(|item| {
            item.unit_category
                .as_ref()
                .map(|source| !failed_set.contains(source))
                .unwrap_or(true)
        })
        .collect::<Vec<_>>();
    news.extend(retried_agencies.items);
    news = dedupe_news(news);

    let mut health = previous
        .source_health
        .into_iter()
        .filter(|item| !failed_set.contains(&item.source) && !is_parliament_health(&item.source))
        .collect::<Vec<_>>();
    health.extend(retried_agencies.health);
    let agencies = FetchResult {
        items: news,
        health,
        warnings: retried_agencies.warnings,
    };
    finalize(options, agencies, retried_parliament).await
}

async fn finalize(
    options: RunOptions,
    mut agencies: FetchResult<NewsItem>,
    mut parliament: FetchResult<ParliamentBriefing>,
) -> Result<(PathBuf, PathBuf, RunSummary)> {
    let mut filtered = vec![];
    for item in &mut agencies.items {
        if assess_news(item, &options.profile) {
            filtered.push(item.clone())
        }
    }
    let mut filtered_p = vec![];
    for item in &mut parliament.items {
        if assess_parliament(item, &options.profile) {
            filtered_p.push(item.clone())
        }
    }
    let texts = agencies.items.iter().map(|x| x.title.clone()).chain(
        parliament
            .items
            .iter()
            .flat_map(|x| [x.title.clone(), x.summary.clone()]),
    );
    let concurrency = std::env::var("UK_NEWS_TRANSLATION_CONCURRENCY")
        .ok()
        .and_then(|x| x.parse().ok())
        .unwrap_or(4);
    let (translations, mut translation_warnings) = TranslationService::new(
        FreeGoogleProvider::default(),
        options.translation_cache.clone(),
        concurrency,
    )
    .translate_all(texts)
    .await;
    export_news(
        &agencies.items,
        &filtered,
        &parliament.items,
        &filtered_p,
        &translations,
        &options.output,
        ExportOptions {
            calendar_mode: options.calendar,
            profile: &options.profile,
        },
    )?;
    let data = RunData {
        news: agencies.items.clone(),
        parliament: parliament.items.clone(),
    };
    let mut health = agencies.health;
    health.append(&mut parliament.health);
    health.sort_by(|a, b| a.source.cmp(&b.source));
    let mut warnings = agencies.warnings;
    warnings.append(&mut parliament.warnings);
    warnings.extend(
        health
            .iter()
            .filter(|item| !item.warning.is_empty())
            .map(|item| item.warning.clone()),
    );
    warnings.append(&mut translation_warnings);
    warnings.sort();
    warnings.dedup();
    let status = if health.iter().all(|x| x.success && x.warning.is_empty()) {
        RunStatus::Complete
    } else {
        RunStatus::Degraded
    };
    let fingerprint = make_data_fingerprint(&agencies.items, &parliament.items);
    let run_id = format!("uk-news-{}_{}", options.since, options.until);
    let summary = RunSummary {
        run_id: run_id.clone(),
        generated_at: Utc::now().to_rfc3339(),
        period_start: options.since.to_string(),
        period_end: options.until.to_string(),
        output_file: options.output.to_string_lossy().into(),
        all_news_count: agencies.items.len(),
        filtered_news_count: filtered.len(),
        parliament_count: parliament.items.len(),
        filtered_parliament_count: filtered_p.len(),
        status,
        warnings,
        data_fingerprint: fingerprint.clone(),
        delivery_id: make_delivery_id(&run_id, status, &fingerprint),
        source_health: health,
        profile_id: options.profile.profile_id.clone(),
        profile_name: options.profile.name.clone(),
        profile_version: options.profile.version,
        profile_hash: profile_hash(&options.profile),
        selected_sources: options.profile.selected_sources.clone(),
        minimum_score: options.profile.minimum_score,
        excel_date_calendar: match options.calendar {
            CalendarMode::Gregorian => "gregorian",
            CalendarMode::Roc => "roc",
        }
        .into(),
    };
    let summary_path = options.output.with_extension("run.json");
    atomic_json(&summary_path, &summary)?;
    atomic_json(&data_path_for_summary(&summary_path), &data)?;
    Ok((options.output, summary_path, summary))
}

fn utc_range(since: NaiveDate, until: NaiveDate) -> (DateTime<Utc>, DateTime<Utc>) {
    (
        DateTime::<Utc>::from_naive_utc_and_offset(since.and_hms_opt(0, 0, 0).unwrap(), Utc),
        DateTime::<Utc>::from_naive_utc_and_offset(
            (until + chrono::Days::new(1)).and_hms_opt(0, 0, 0).unwrap(),
            Utc,
        ),
    )
}

fn data_path_for_summary(path: &Path) -> PathBuf {
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("run.run.json");
    let stem = name.strip_suffix(".run.json").unwrap_or(name);
    path.with_file_name(format!("{stem}.run.data.json"))
}

pub fn read_run_data(summary_path: &Path) -> Result<RunData> {
    let path = data_path_for_summary(summary_path);
    serde_json::from_str(
        &fs::read_to_string(&path)
            .with_context(|| format!("讀取本機執行資料：{}", path.display()))?,
    )
    .context("解析本機執行資料")
}

fn is_parliament_health(source: &str) -> bool {
    source.contains("Parliament")
        || source.contains("Commons")
        || source.contains("Lords")
        || source.contains("POST")
}

fn dedupe_news(mut items: Vec<NewsItem>) -> Vec<NewsItem> {
    items.sort_by_key(|item| std::cmp::Reverse(item.published_at));
    let mut seen = HashSet::new();
    items
        .into_iter()
        .filter(|item| {
            let key = if !item.link.trim().is_empty() {
                item.link.trim_end_matches('/').to_lowercase()
            } else {
                format!(
                    "{}:{}:{}",
                    item.unit_category.as_deref().unwrap_or(&item.agency_en),
                    item.published_at.date_naive(),
                    item.title.to_lowercase()
                )
            };
            seen.insert(key)
        })
        .collect()
}

fn atomic_json(path: &Path, value: &impl serde::Serialize) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension(format!(
        "{}.tmp",
        path.extension().and_then(|x| x.to_str()).unwrap_or("json")
    ));
    fs::write(&tmp, format!("{}\n", serde_json::to_string_pretty(value)?))?;
    fs::rename(tmp, path)?;
    Ok(())
}

pub fn default_run_options(since: NaiveDate, until: NaiveDate, output: PathBuf) -> RunOptions {
    RunOptions {
        since,
        until,
        output,
        workers: 6,
        profile: default_profile(),
        calendar: CalendarMode::Gregorian,
        translation_cache: PathBuf::from(".uk_news_translation_cache.json"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retry_sidecar_follows_summary_name() {
        assert_eq!(
            data_path_for_summary(Path::new("/tmp/report.run.json")),
            PathBuf::from("/tmp/report.run.data.json")
        );
    }
}
