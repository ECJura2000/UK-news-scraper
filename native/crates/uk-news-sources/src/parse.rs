use anyhow::{anyhow, Result};
use chrono::{DateTime, NaiveDate, Utc};
use feed_rs::parser;
use scraper::{Html, Selector};
use serde_json::Value;
use uk_news_core::{Agency, ContentType, NewsItem};
use url::Url;

pub fn content_type_for_link(link: &str, title: &str) -> ContentType {
    let text = format!("{} {}", link.to_lowercase(), title.to_lowercase());
    if text.contains("/guidance/") || text.contains("guidance") || text.contains("/collection/") {
        ContentType::Guidance
    } else if text.contains("report") {
        ContentType::Report
    } else if text.contains("/government/publications/")
        || text.contains("/publications/")
        || text.contains("consultation")
    {
        ContentType::Publication
    } else {
        ContentType::News
    }
}

fn allowed(agency: &Agency, link: &str) -> bool {
    let Some(link_host) = Url::parse(link)
        .ok()
        .and_then(|url| url.host_str().map(normalize_host))
    else {
        return false;
    };
    let official_hosts = std::iter::once(&agency.homepage)
        .chain(agency.news_pages.iter())
        .chain(agency.official_pages.iter())
        .filter_map(|value| Url::parse(value).ok())
        .filter_map(|url| url.host_str().map(normalize_host));
    if !official_hosts.into_iter().any(|host| {
        link_host == host
            || link_host.ends_with(&format!(".{host}"))
            || host.ends_with(&format!(".{link_host}"))
    }) {
        return false;
    }
    agency.link_include_patterns.is_empty()
        || agency
            .link_include_patterns
            .iter()
            .any(|pattern| link.contains(pattern))
}

fn normalize_host(host: &str) -> String {
    let lower = host.to_lowercase();
    lower.strip_prefix("www.").unwrap_or(&lower).to_string()
}

pub fn parse_feed_document(
    bytes: &[u8],
    agency: &Agency,
    source: &str,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
) -> Result<Vec<NewsItem>> {
    let feed = parser::parse(bytes)?;
    let mut out = vec![];
    for entry in feed.entries {
        let published = entry
            .published
            .or(entry.updated)
            .ok_or_else(|| anyhow!("entry has no date"));
        let Ok(published) = published else { continue };
        if published < since || published >= until {
            continue;
        }
        let title = entry
            .title
            .map(|x| x.content.trim().to_string())
            .unwrap_or_default();
        let link = entry
            .links
            .first()
            .map(|x| x.href.clone())
            .unwrap_or_default();
        if title.is_empty() || link.is_empty() || !allowed(agency, &link) {
            continue;
        }
        let summary = entry.summary.map(|x| x.content).unwrap_or_default();
        out.push(NewsItem {
            agency: agency.display_name(),
            agency_en: agency.name_en.clone(),
            unit_category: Some(agency.short_name.clone()),
            title: title.clone(),
            link: link.clone(),
            published_at: published,
            summary,
            source_feed: source.into(),
            matched_topics: vec![],
            matched_keywords: vec![],
            title_matched_keywords: vec![],
            summary_matched_keywords: vec![],
            core_matched_keywords: vec![],
            general_matched_keywords: vec![],
            supporting_matched_keywords: vec![],
            title_keyword_strengths: Default::default(),
            summary_keyword_strengths: Default::default(),
            relevance_score: 0,
            relevance_level: String::new(),
            content_type: content_type_for_link(&link, &title),
        });
    }
    Ok(out)
}

fn parse_date(text: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(text)
        .ok()
        .map(|x| x.with_timezone(&Utc))
        .or_else(|| {
            DateTime::parse_from_rfc2822(text)
                .ok()
                .map(|x| x.with_timezone(&Utc))
        })
        .or_else(|| {
            NaiveDate::parse_from_str(text.trim(), "%d %B %Y")
                .ok()
                .and_then(|x| x.and_hms_opt(0, 0, 0))
                .map(|x| x.and_utc())
        })
        .or_else(|| {
            NaiveDate::parse_from_str(text.trim(), "%Y-%m-%d")
                .ok()
                .and_then(|x| x.and_hms_opt(0, 0, 0))
                .map(|x| x.and_utc())
        })
}

fn meta(doc: &Html, selectors: &[&str]) -> Option<String> {
    for raw in selectors {
        let sel = Selector::parse(raw).ok()?;
        if let Some(x) = doc.select(&sel).next() {
            if let Some(v) = x.value().attr("content") {
                if !v.trim().is_empty() {
                    return Some(v.trim().into());
                }
            }
            if let Some(v) = x.value().attr("datetime") {
                if !v.trim().is_empty() {
                    return Some(v.trim().into());
                }
            }
            let t = x.text().collect::<Vec<_>>().join(" ").trim().to_string();
            if !t.is_empty() {
                return Some(t);
            }
        }
    }
    None
}

fn json_ld_date(doc: &Html) -> Option<String> {
    let sel = Selector::parse("script[type='application/ld+json']").ok()?;
    for node in doc.select(&sel) {
        if let Ok(value) = serde_json::from_str::<Value>(&node.text().collect::<String>()) {
            if let Some(v) = find_json_string(&value, "datePublished") {
                return Some(v);
            }
        }
    }
    None
}
fn find_json_string(value: &Value, key: &str) -> Option<String> {
    match value {
        Value::Object(map) => map
            .get(key)
            .and_then(Value::as_str)
            .map(Into::into)
            .or_else(|| map.values().find_map(|v| find_json_string(v, key))),
        Value::Array(a) => a.iter().find_map(|v| find_json_string(v, key)),
        _ => None,
    }
}

pub fn parse_official_html(
    html: &str,
    agency: &Agency,
    page_url: &str,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
) -> Vec<NewsItem> {
    let doc = Html::parse_document(html);
    let mut out = vec![];
    let title = meta(&doc, &["meta[property='og:title']", "h1", "title"]);
    let summary = meta(
        &doc,
        &[
            "meta[name='description']",
            "meta[property='og:description']",
        ],
    )
    .unwrap_or_default();
    let page_path = Url::parse(page_url)
        .ok()
        .map(|x| x.path().to_lowercase())
        .unwrap_or_default();
    let content_page = [
        "/collection/",
        "/guidance/",
        "/government/publications/",
        "/government/consultations/",
        "/report",
    ]
    .iter()
    .any(|marker| page_path.contains(marker));
    let explicit_article_date = meta(
        &doc,
        &[
            "meta[property='article:published_time']",
            "meta[name='datePublished']",
        ],
    );
    let date = explicit_article_date
        .clone()
        .or_else(|| json_ld_date(&doc))
        .or_else(|| {
            meta(
                &doc,
                &[
                    "meta[property='article:published_time']",
                    "meta[name='date']",
                    "time[datetime]",
                    "time",
                ],
            )
        });
    if content_page || explicit_article_date.is_some() {
        if let (Some(title), Some(date)) = (title, date) {
            if let Some(published_at) = parse_date(&date) {
                if published_at >= since && published_at < until && title.len() >= 12 {
                    out.push(news(
                        agency,
                        title,
                        page_url.into(),
                        published_at,
                        page_url.into(),
                        summary,
                    ))
                }
            }
        }
    }
    let container =
        Selector::parse("article, li, .govuk-document-list li, .search-result, .card").unwrap();
    let anchor = Selector::parse("h2 a[href], h3 a[href], h4 a[href], a[href]").unwrap();
    let time = Selector::parse("time").unwrap();
    let base = Url::parse(page_url).ok();
    for c in doc.select(&container) {
        let Some(a) = c.select(&anchor).next() else {
            continue;
        };
        let title = a.text().collect::<Vec<_>>().join(" ").trim().to_string();
        if title.len() < 12 {
            continue;
        }
        let Some(href) = a.value().attr("href") else {
            continue;
        };
        let link = base
            .as_ref()
            .and_then(|b| b.join(href).ok())
            .map(|x| x.to_string())
            .unwrap_or_else(|| href.into());
        if Url::parse(&link)
            .ok()
            .and_then(|x| x.host_str().map(str::to_owned))
            != base.as_ref().and_then(|x| x.host_str().map(str::to_owned))
        {
            continue;
        }
        if !allowed(agency, &link)
            || link
                .to_lowercase()
                .split('?')
                .next()
                .is_some_and(|x| x.ends_with(".pdf"))
        {
            continue;
        }
        let Some(t) = c.select(&time).next() else {
            continue;
        };
        let raw = t
            .value()
            .attr("datetime")
            .unwrap_or_else(|| t.text().next().unwrap_or(""));
        let Some(published_at) = parse_date(raw) else {
            continue;
        };
        if published_at < since || published_at >= until {
            continue;
        }
        out.push(news(
            agency,
            title,
            link,
            published_at,
            page_url.into(),
            String::new(),
        ))
    }
    dedupe(out)
}

fn news(
    a: &Agency,
    title: String,
    link: String,
    published_at: DateTime<Utc>,
    source_feed: String,
    summary: String,
) -> NewsItem {
    NewsItem {
        agency: a.display_name(),
        agency_en: a.name_en.clone(),
        unit_category: Some(a.short_name.clone()),
        content_type: content_type_for_link(&link, &title),
        title,
        link,
        published_at,
        summary,
        source_feed,
        matched_topics: vec![],
        matched_keywords: vec![],
        title_matched_keywords: vec![],
        summary_matched_keywords: vec![],
        core_matched_keywords: vec![],
        general_matched_keywords: vec![],
        supporting_matched_keywords: vec![],
        title_keyword_strengths: Default::default(),
        summary_keyword_strengths: Default::default(),
        relevance_score: 0,
        relevance_level: String::new(),
    }
}
pub fn dedupe(items: Vec<NewsItem>) -> Vec<NewsItem> {
    let mut seen = std::collections::HashSet::new();
    let mut items = items;
    items.sort_by_key(|item| std::cmp::Reverse(item.published_at));
    items
        .into_iter()
        .filter(|x| {
            let link = x.link.trim().trim_end_matches('/').to_lowercase();
            let key = if !link.is_empty() {
                format!("link:{link}")
            } else {
                let title = x
                    .title
                    .to_lowercase()
                    .replace(['–', '—'], "-")
                    .split_whitespace()
                    .collect::<Vec<_>>()
                    .join(" ");
                format!(
                    "fallback:{}:{}:{title}",
                    x.agency.to_lowercase(),
                    x.date_text()
                )
            };
            seen.insert(key)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;
    #[test]
    fn ncsc_guidance_fixture() {
        let a = Agency {
            name_zh: "國家網路安全中心".into(),
            name_en: "National Cyber Security Centre".into(),
            short_name: "NCSC".into(),
            homepage: "https://www.ncsc.gov.uk".into(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let html = r#"<html><head><script type="application/ld+json">{"datePublished":"2026-07-28"}</script></head><body><h1>Recovering from a highly disruptive cyber attack</h1></body></html>"#;
        let items=parse_official_html(html,&a,"https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation/recovering",Utc.with_ymd_and_hms(2026,7,1,0,0,0).unwrap(),Utc.with_ymd_and_hms(2026,8,1,0,0,0).unwrap());
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].date_text(), "2026-07-28");
        assert_eq!(items[0].content_type, ContentType::Guidance);
    }

    #[test]
    fn gov_feed_accepts_document_types_and_rejects_external_domains() {
        let agency = Agency {
            name_zh: "部會".into(),
            name_en: "Department".into(),
            short_name: "TEST".into(),
            homepage: "https://www.gov.uk/government/organisations/test".into(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![
                "/guidance/".into(),
                "/government/publications/".into(),
                "/government/consultations/".into(),
            ],
            official_pages: vec![],
        };
        let xml = r#"<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
          <title>Fixture</title><id>fixture</id><updated>2026-07-28T00:00:00Z</updated>
          <entry><title>Official guidance item</title><id>1</id><updated>2026-07-28T01:00:00Z</updated><link href="https://www.gov.uk/guidance/official-item"/></entry>
          <entry><title>Official publication item</title><id>2</id><updated>2026-07-28T02:00:00Z</updated><link href="https://www.gov.uk/government/publications/official-item"/></entry>
          <entry><title>Official consultation item</title><id>3</id><updated>2026-07-28T03:00:00Z</updated><link href="https://www.gov.uk/government/consultations/official-item"/></entry>
          <entry><title>External guidance item</title><id>4</id><updated>2026-07-28T04:00:00Z</updated><link href="https://evil.example/guidance/item"/></entry>
        </feed>"#;
        let items = parse_feed_document(
            xml.as_bytes(),
            &agency,
            "fixture",
            Utc.with_ymd_and_hms(2026, 7, 28, 0, 0, 0).unwrap(),
            Utc.with_ymd_and_hms(2026, 7, 29, 0, 0, 0).unwrap(),
        )
        .unwrap();
        assert_eq!(items.len(), 3);
        assert_eq!(items[0].content_type, ContentType::Guidance);
        assert_eq!(items[1].content_type, ContentType::Publication);
        assert_eq!(items[2].content_type, ContentType::Publication);
    }

    #[test]
    fn official_html_requires_date_and_period() {
        let agency = Agency {
            name_zh: "機關".into(),
            name_en: "Agency".into(),
            short_name: "A".into(),
            homepage: "https://official.example/".into(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let since = Utc.with_ymd_and_hms(2026, 7, 28, 0, 0, 0).unwrap();
        let until = Utc.with_ymd_and_hms(2026, 7, 29, 0, 0, 0).unwrap();
        assert!(parse_official_html(
            "<h1>Guidance without a date</h1>",
            &agency,
            "https://official.example/guidance/no-date",
            since,
            until,
        )
        .is_empty());
        assert!(parse_official_html(
            "<h1>Guidance outside period</h1><time datetime='2026-07-27'>27 July 2026</time>",
            &agency,
            "https://official.example/guidance/old",
            since,
            until,
        )
        .is_empty());
    }
}
