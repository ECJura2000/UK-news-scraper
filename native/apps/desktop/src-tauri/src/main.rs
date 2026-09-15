use anyhow::{Context, Result};
use chrono::{Datelike, Days, NaiveDate, Utc};
use clap::{Args, Parser, Subcommand};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::OnceLock;
use tokio::sync::Mutex;
use uk_news_app::{
    claim, complete, default_profile, execute, load_profile, release, retry_failed_sources, status,
    RunOptions,
};
use uk_news_export::CalendarMode;

#[derive(Parser)]
#[command(
    name = "UKNewsScraper",
    about = "抓取英國官方新聞、Guidance、Report 與國會研究資料"
)]
struct Cli {
    #[arg(value_name = "PERIOD")]
    period: Vec<String>,
    #[arg(long)]
    days: Option<u64>,
    #[arg(long)]
    since: Option<String>,
    #[arg(long)]
    until: Option<String>,
    #[arg(long)]
    output: Option<PathBuf>,
    #[arg(long, default_value_t = 6)]
    workers: usize,
    #[arg(long)]
    profile: Option<String>,
    #[arg(long,value_enum,default_value_t=CalendarArg::Gregorian)]
    excel_calendar: CalendarArg,
    #[arg(long)]
    ui: bool,
    #[arg(long)]
    check_runtime: bool,
    #[arg(long)]
    export_organisation_template: Option<PathBuf>,
    #[arg(long)]
    open_organisation_folder: bool,
    #[command(subcommand)]
    command: Option<Command>,
}
#[derive(clap::ValueEnum, Clone, Copy)]
enum CalendarArg {
    Gregorian,
    Roc,
}
impl From<CalendarArg> for CalendarMode {
    fn from(x: CalendarArg) -> Self {
        match x {
            CalendarArg::Gregorian => Self::Gregorian,
            CalendarArg::Roc => Self::Roc,
        }
    }
}
#[derive(Subcommand)]
enum Command {
    DeliveryRegistry(Delivery),
}
#[derive(Args)]
struct Delivery {
    #[arg(long, global = true)]
    registry: Option<PathBuf>,
    #[command(subcommand)]
    command: DeliveryCommand,
}
#[derive(Subcommand)]
enum DeliveryCommand {
    Claim {
        #[arg(long)]
        summary: PathBuf,
    },
    Complete {
        #[arg(long)]
        delivery_id: String,
        #[arg(long)]
        message_id: String,
    },
    Release {
        #[arg(long)]
        delivery_id: String,
    },
    Status {
        #[arg(long)]
        delivery_id: Option<String>,
        #[arg(long)]
        state: Option<String>,
    },
    Recover {
        #[arg(long)]
        delivery_id: String,
        #[arg(long)]
        confirm_release: bool,
    },
}

fn main() {
    if let Err(e) = entry() {
        eprintln!("[error] {e:#}");
        std::process::exit(1)
    }
}
fn entry() -> Result<()> {
    let cli = Cli::parse();
    if let Some(Command::DeliveryRegistry(d)) = cli.command {
        return delivery(d);
    }
    if let Some(path) = cli.export_organisation_template {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&path, uk_news_core::ORGANISATION_TEMPLATE)?;
        println!("{}", path.display());
        return Ok(());
    }
    if cli.open_organisation_folder {
        let path = uk_news_core::external_registry_dir();
        std::fs::create_dir_all(&path)?;
        open_local_path(&path)?;
        println!("{}", path.display());
        return Ok(());
    }
    if cli.check_runtime {
        let registry = uk_news_sources::organisation_registry();
        println!(
            "原生執行環境檢查通過；scrapers={} runtime=rust fingerprint=v4 registry={} module_errors={}",
            registry.modules.len(), registry.registry_hash, registry.errors.len()
        );
        return Ok(());
    }
    if cli.ui
        || std::env::args().len() == 1 && std::env::var_os("UK_NEWS_DESKTOP_DEFAULT").is_some()
    {
        return launch_ui();
    }
    let (since, until) = resolve_dates(&cli)?;
    let profile = load_profile(cli.profile.as_deref())?;
    let output = cli
        .output
        .unwrap_or_else(|| default_output(since, until, &profile.profile_id));
    let cache = cache_path();
    let opts = RunOptions {
        since,
        until,
        output,
        workers: cli.workers,
        profile,
        calendar: cli.excel_calendar.into(),
        translation_cache: cache,
    };
    let result = tokio::runtime::Runtime::new()?.block_on(execute(opts))?;
    println!("Run ID：{}", result.2.run_id);
    println!("全部新聞：{} 筆", result.2.all_news_count);
    println!("Excel：{}", result.0.display());
    println!("執行摘要：{}", result.1.display());
    Ok(())
}
fn open_local_path(path: &std::path::Path) -> Result<()> {
    #[cfg(target_os = "macos")]
    let status = std::process::Command::new("open").arg(path).status()?;
    #[cfg(target_os = "windows")]
    let status = std::process::Command::new("explorer").arg(path).status()?;
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let status = std::process::Command::new("xdg-open").arg(path).status()?;
    if !status.success() {
        anyhow::bail!("無法開啟 {}", path.display());
    }
    Ok(())
}
fn delivery(d: Delivery) -> Result<()> {
    let registry = d.registry.as_deref();
    let value = match d.command {
        DeliveryCommand::Claim { summary } => claim(&summary, registry)?,
        DeliveryCommand::Complete {
            delivery_id,
            message_id,
        } => complete(&delivery_id, &message_id, registry)?,
        DeliveryCommand::Release { delivery_id } => {
            serde_json::json!({"released":release(&delivery_id,registry)?})
        }
        DeliveryCommand::Status { delivery_id, state } => {
            status(delivery_id.as_deref(), state.as_deref(), registry)?
        }
        DeliveryCommand::Recover {
            delivery_id,
            confirm_release,
        } => {
            if !confirm_release {
                anyhow::bail!("recover 需要明確確認：--confirm-release")
            }
            serde_json::json!({"delivery_id":delivery_id,"released":release(&delivery_id,registry)?})
        }
    };
    println!("{}", serde_json::to_string(&value)?);
    Ok(())
}
fn parse_date(s: &str) -> Result<NaiveDate> {
    NaiveDate::parse_from_str(s, "%Y-%m-%d")
        .or_else(|_| NaiveDate::parse_from_str(s, "%Y%m%d"))
        .with_context(|| format!("日期格式錯誤：{s}"))
}
fn resolve_dates(cli: &Cli) -> Result<(NaiveDate, NaiveDate)> {
    let today = Utc::now()
        .with_timezone(&chrono_tz::Asia::Taipei)
        .date_naive();
    if let Some(s) = &cli.since {
        return Ok((
            parse_date(s)?,
            cli.until
                .as_deref()
                .map(parse_date)
                .transpose()?
                .unwrap_or(today),
        ));
    }
    if !cli.period.is_empty() {
        let joined = cli.period.join("").replace('～', "~").replace(' ', "");
        if let Some((a, b)) = joined.split_once('~') {
            return Ok((parse_date(a)?, parse_date(b)?));
        }
        if let Ok(days) = joined.parse::<u64>() {
            return Ok((
                today
                    .checked_sub_days(Days::new(days.saturating_sub(1)))
                    .unwrap(),
                today,
            ));
        }
        return Ok((
            parse_date(&joined)?,
            cli.until
                .as_deref()
                .map(parse_date)
                .transpose()?
                .unwrap_or(today),
        ));
    }
    let days = cli.days.unwrap_or(14);
    Ok((
        today
            .checked_sub_days(Days::new(days.saturating_sub(1)))
            .unwrap(),
        today,
    ))
}
fn default_output(since: NaiveDate, until: NaiveDate, profile_id: &str) -> PathBuf {
    let dir = std::env::var_os("UK_NEWS_OUTPUT_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            let development = std::env::current_exe()
                .ok()
                .is_some_and(|path| path.components().any(|part| part.as_os_str() == "target"));
            if development {
                std::env::current_dir().unwrap().join("新聞放置區")
            } else {
                std::env::var_os("HOME")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| PathBuf::from("."))
                    .join("Desktop/UK新聞抓取/新聞放置區")
            }
        });
    let suffix = if profile_id == "uk-tech-law" {
        String::new()
    } else {
        format!("_{profile_id}")
    };
    dir.join(format!(
        "{:04}{:02}{:02}-{:04}{:02}{:02}_UK新聞查詢{suffix}.xlsx",
        since.year(),
        since.month(),
        since.day(),
        until.year(),
        until.month(),
        until.day()
    ))
}
fn cache_path() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".cache/uk-news-scraper/translations.json")
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UiRunRequest {
    since: String,
    until: String,
    output: String,
    workers: usize,
    profile_path: Option<String>,
    calendar: String,
    selected_sources: Vec<String>,
    minimum_score: Option<i32>,
    profile: Option<uk_news_core::FilterProfile>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct UiRetryRequest {
    run: UiRunRequest,
    summary_path: String,
}
#[derive(Serialize)]
struct UiRunResult {
    workbook_path: String,
    summary_path: String,
    summary: uk_news_core::RunSummary,
    news: Vec<uk_news_core::NewsItem>,
    parliament: Vec<uk_news_core::ParliamentBriefing>,
}
#[derive(Serialize)]
struct OrganisationRegistryStatus {
    modules: Vec<uk_news_core::OrganisationModuleSummary>,
    errors: Vec<String>,
    registry_hash: String,
    external_dir: String,
}
static ACTIVE_RUN: OnceLock<Mutex<Option<tokio::task::AbortHandle>>> = OnceLock::new();
#[tauri::command]
fn source_catalog() -> Vec<uk_news_core::Agency> {
    uk_news_sources::agencies()
}
#[tauri::command]
fn organisation_registry_status() -> OrganisationRegistryStatus {
    let registry = uk_news_sources::organisation_registry();
    OrganisationRegistryStatus {
        modules: registry.module_summaries(),
        errors: registry.errors,
        registry_hash: registry.registry_hash,
        external_dir: uk_news_core::external_registry_dir().display().to_string(),
    }
}
#[tauri::command]
fn export_organisation_template(path: String) -> Result<String, String> {
    let target = PathBuf::from(path);
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    std::fs::write(&target, uk_news_core::ORGANISATION_TEMPLATE)
        .map_err(|error| error.to_string())?;
    Ok(target.display().to_string())
}
#[tauri::command]
fn organisation_folder() -> Result<String, String> {
    let path = uk_news_core::external_registry_dir();
    std::fs::create_dir_all(&path).map_err(|error| error.to_string())?;
    Ok(path.display().to_string())
}
#[tauri::command]
fn built_in_profile() -> uk_news_core::FilterProfile {
    default_profile()
}
#[tauri::command]
fn list_profiles() -> Result<Vec<uk_news_core::FilterProfile>, String> {
    uk_news_app::load_profiles().map_err(|e| e.to_string())
}
#[tauri::command]
fn profile_load_report() -> uk_news_app::ProfileLoadReport {
    uk_news_app::load_profiles_with_recovery()
}
#[tauri::command]
fn save_profile(profile: uk_news_core::FilterProfile) -> Result<String, String> {
    uk_news_app::save_profile(profile)
        .map(|p| p.display().to_string())
        .map_err(|e| e.to_string())
}
#[tauri::command]
fn delete_profile(profile_id: String) -> Result<bool, String> {
    uk_news_app::delete_profile(&profile_id).map_err(|e| e.to_string())
}
#[tauri::command]
async fn run_scraper(request: UiRunRequest) -> Result<UiRunResult, String> {
    run_task(request, None).await
}
#[tauri::command]
async fn retry_failed(request: UiRetryRequest) -> Result<UiRunResult, String> {
    run_task(request.run, Some(PathBuf::from(request.summary_path))).await
}
async fn run_task(
    request: UiRunRequest,
    previous_summary: Option<PathBuf>,
) -> Result<UiRunResult, String> {
    let since = parse_date(&request.since).map_err(|e| e.to_string())?;
    let until = parse_date(&request.until).map_err(|e| e.to_string())?;
    let mut profile = if let Some(profile) = request.profile.clone() {
        uk_news_app::validate_profile(&profile).map_err(|e| e.to_string())?;
        profile
    } else {
        load_profile(request.profile_path.as_deref()).map_err(|e| e.to_string())?
    };
    if !request.selected_sources.is_empty() {
        profile.selected_sources = request.selected_sources;
    }
    if let Some(minimum_score) = request.minimum_score {
        profile.minimum_score = minimum_score.max(1);
    }
    let calendar = if request.calendar == "roc" {
        CalendarMode::Roc
    } else {
        CalendarMode::Gregorian
    };
    let options = RunOptions {
        since,
        until,
        output: PathBuf::from(request.output),
        workers: request.workers.max(1),
        profile,
        calendar,
        translation_cache: cache_path(),
    };
    let task = tokio::spawn(async move {
        if let Some(summary) = previous_summary {
            retry_failed_sources(options, &summary).await
        } else {
            execute(options).await
        }
    });
    let active = ACTIVE_RUN.get_or_init(|| Mutex::new(None));
    *active.lock().await = Some(task.abort_handle());
    let outcome = task.await;
    *active.lock().await = None;
    let (w, s, summary) = outcome
        .map_err(|e| {
            if e.is_cancelled() {
                "執行已取消".into()
            } else {
                e.to_string()
            }
        })?
        .map_err(|e| format!("{e:#}"))?;
    let data = uk_news_app::read_run_data(&s).map_err(|e| format!("{e:#}"))?;
    Ok(UiRunResult {
        workbook_path: w.display().to_string(),
        summary_path: s.display().to_string(),
        summary,
        news: data.news,
        parliament: data.parliament,
    })
}
#[tauri::command]
async fn cancel_run() -> bool {
    let active = ACTIVE_RUN.get_or_init(|| Mutex::new(None));
    if let Some(handle) = active.lock().await.take() {
        handle.abort();
        true
    } else {
        false
    }
}

#[tauri::command]
fn recent_runs(output_dir: String) -> Vec<uk_news_core::RunSummary> {
    let Ok(entries) = std::fs::read_dir(output_dir) else {
        return vec![];
    };
    let mut runs = entries
        .filter_map(Result::ok)
        .filter(|e| {
            e.path().extension().is_some_and(|x| x == "json")
                && e.path().to_string_lossy().ends_with(".run.json")
        })
        .filter_map(|e| std::fs::read_to_string(e.path()).ok())
        .filter_map(|x| serde_json::from_str::<uk_news_core::RunSummary>(&x).ok())
        .collect::<Vec<_>>();
    runs.sort_by(|a, b| b.generated_at.cmp(&a.generated_at));
    runs.truncate(20);
    runs
}
fn launch_ui() -> Result<()> {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            source_catalog,
            organisation_registry_status,
            export_organisation_template,
            organisation_folder,
            built_in_profile,
            list_profiles,
            profile_load_report,
            save_profile,
            delete_profile,
            run_scraper,
            retry_failed,
            cancel_run,
            recent_runs
        ])
        .run(tauri::generate_context!())
        .map_err(Into::into)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn range_accepts_full_width_tilde() {
        let cli = Cli::try_parse_from(["x", "20160501～20160515"]).unwrap();
        let (a, b) = resolve_dates(&cli).unwrap();
        assert_eq!(a.to_string(), "2016-05-01");
        assert_eq!(b.to_string(), "2016-05-15");
    }
}
