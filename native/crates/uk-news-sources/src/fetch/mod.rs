use crate::transport::Transport;
use crate::{agencies, content_type_for_link, parse_feed_document, parse_official_html};
use chrono::{DateTime, NaiveDate, Utc};
use feed_rs::parser;
use futures::stream::{self, StreamExt};
use regex::Regex;
use scraper::{Html, Selector};
use serde_json::Value;
use std::{collections::HashSet, sync::Arc, time::Instant};
use uk_news_core::{
    Agency, ContentType, EndpointObservation, NewsItem, ParliamentBriefing, SourceHealth,
};

pub struct FetchResult<T> {
    pub items: Vec<T>,
    pub health: Vec<SourceHealth>,
    pub warnings: Vec<String>,
}

pub type SourceProgress = Arc<dyn Fn(&SourceHealth) + Send + Sync>;

fn last_fetched_at(observations: &[EndpointObservation]) -> String {
    observations
        .last()
        .map(|observation| observation.fetched_at.clone())
        .unwrap_or_else(|| Utc::now().to_rfc3339())
}

fn page_has_in_range_date(html: &str, since: DateTime<Utc>, until: DateTime<Utc>) -> bool {
    let start_date = (since + chrono::Duration::hours(8)).date_naive();
    let end_date = (until + chrono::Duration::hours(8)).date_naive();
    let document = Html::parse_document(html);
    let selector = Selector::parse(
        "time[datetime], meta[property='article:published_time'], meta[name='datePublished']",
    )
    .expect("static selector");
    document.select(&selector).any(|node| {
        let raw = node
            .value()
            .attr("datetime")
            .or_else(|| node.value().attr("content"));
        raw.and_then(|value| value.get(..10))
            .and_then(|value| NaiveDate::parse_from_str(value, "%Y-%m-%d").ok())
            .is_some_and(|date| date >= start_date && date < end_date)
    })
}

fn collect_out_of_period_links(
    feed: &feed_rs::model::Feed,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    excluded: &mut HashSet<String>,
) {
    for entry in &feed.entries {
        if entry
            .published
            .or(entry.updated)
            .is_some_and(|date| date < since || date >= until)
        {
            if let Some(link) = entry.links.first() {
                excluded.insert(link.href.trim_end_matches('/').to_string());
            }
        }
    }
}

fn exclude_precise_out_of_period_links(items: &mut Vec<NewsItem>, excluded: &HashSet<String>) {
    items.retain(|item| !excluded.contains(item.link.trim_end_matches('/')));
}

fn round_duration(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}

mod agency;
mod fallback;
mod parliament;

pub use agency::{fetch_agencies, fetch_agencies_with_progress};
pub use parliament::fetch_parliament;
