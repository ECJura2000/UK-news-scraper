//! Inspect live source records without translation or workbook generation.
use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use std::{env, fs, sync::Arc};

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    let profile: Value = serde_json::from_slice(&fs::read(args.get(1).context("profile path")?)?)?;
    let selected: Vec<String> = serde_json::from_value(profile["selected_sources"].clone())?;
    let since =
        DateTime::parse_from_rfc3339(args.get(2).context("since timestamp")?)?.with_timezone(&Utc);
    let until =
        DateTime::parse_from_rfc3339(args.get(3).context("until timestamp")?)?.with_timezone(&Utc);
    let progress: uk_news_sources::SourceProgress = Arc::new(|health| {
        eprintln!(
            "source={} success={} items={} duration={} warning={}",
            health.source,
            health.success,
            health.item_count,
            health.duration_seconds,
            health.warning
        );
    });
    let result =
        uk_news_sources::fetch_agencies_with_progress(since, until, 6, &selected, Some(progress))
            .await;
    println!(
        "{}",
        serde_json::to_string(
            &json!({"items": result.items, "health": result.health, "warnings": result.warnings})
        )?
    );
    Ok(())
}
