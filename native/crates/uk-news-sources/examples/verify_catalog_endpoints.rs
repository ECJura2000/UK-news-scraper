//! Replay saved official endpoint bodies through the production Rust parsers.
use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use std::{env, fs};
use uk_news_core::Agency;
use uk_news_sources::{parse_catalog_news_index, parse_feed_document};

fn main() -> Result<()> {
    let path = env::args()
        .nth(1)
        .context("expected audit replay bundle path")?;
    let bundle: Value = serde_json::from_slice(&fs::read(path)?)?;
    let since = DateTime::parse_from_rfc3339("1990-01-01T00:00:00Z")?.with_timezone(&Utc);
    let until = DateTime::parse_from_rfc3339(bundle["until"].as_str().context("until")?)?
        .with_timezone(&Utc);
    let mut output = vec![];
    for source in bundle["sources"].as_array().context("sources")? {
        let agency = Agency {
            name_zh: source["name_zh"].as_str().unwrap_or_default().into(),
            name_en: source["name_en"].as_str().context("name_en")?.into(),
            short_name: source["id"].as_str().context("id")?.into(),
            homepage: source["homepage"].as_str().context("homepage")?.into(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let endpoint = source["endpoint"].as_str().context("endpoint")?;
        let body = fs::read(source["body_path"].as_str().context("body_path")?)?;
        let parsed = match source["adapter"].as_str() {
            Some("feed") => parse_feed_document(&body, &agency, endpoint, since, until),
            Some("html_news") => Ok(parse_catalog_news_index(
                &String::from_utf8_lossy(&body),
                &agency,
                endpoint,
                since,
                until,
            )),
            _ => continue,
        };
        match parsed {
            Ok(items) => output.push(json!({"id": agency.short_name, "items": items.into_iter().map(|item| {
                json!({"title": item.title, "link": item.link, "published_at": item.published_at.to_rfc3339(),
                       "content_type": item.content_type, "summary": item.summary})
            }).collect::<Vec<_>>() })),
            Err(error) => output.push(json!({"id": agency.short_name, "error": error.to_string(), "items": []})),
        }
    }
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
