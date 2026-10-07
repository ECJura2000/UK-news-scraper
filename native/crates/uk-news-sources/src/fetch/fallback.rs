use super::*;

pub(super) async fn google_news_fallback(
    transport: &Transport,
    agency: &Agency,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    observations: &mut Vec<EndpointObservation>,
) -> Result<Vec<NewsItem>, String> {
    let queries: &[&str] = match agency.short_name.as_str() {
        "Ofcom" => &[
            "site:ofcom.org.uk Ofcom",
            "site:ofcom.org.uk \"Ofcom statement\"",
            "site:ofcom.org.uk \"Ofcom consultation\"",
            "site:ofcom.org.uk \"Ofcom update\"",
            "site:ofcom.org.uk \"Ofcom news\"",
            "site:ofcom.org.uk \"Ofcom report\"",
        ],
        "NPSA" => &["site:npsa.gov.uk NPSA"],
        "Electoral Commission" => &["site:electoralcommission.org.uk Electoral Commission"],
        _ => &[],
    };
    let mut items = vec![];
    let ofcom_suffix = Regex::new(r"\s+-\s+(?:Ofcom\s+-\s+)?www\.ofcom\.org\.uk$").unwrap();
    let npsa_suffix =
        Regex::new(r"(?i)\s+-\s+National Protective Security Authority(?:\s+\|\s+NPSA)?$").unwrap();
    let electoral_suffix = Regex::new(r"(?i)\s+-\s+Electoral Commission$").unwrap();
    for query in queries {
        let encoded = query
            .as_bytes()
            .iter()
            .map(|byte| match byte {
                b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                    (*byte as char).to_string()
                }
                _ => format!("%{byte:02X}"),
            })
            .collect::<String>();
        let source =
            format!("https://news.google.com/rss/search?q={encoded}&hl=en-GB&gl=GB&ceid=GB:en");
        let bytes = transport
            .bytes(transport.get(&source), observations)
            .await?;
        let feed = parser::parse(&bytes[..]).map_err(|e| e.to_string())?;
        // feed-rs does not retain RSS <source url>; preserve it for publisher checks.
        let publishers = rss_publishers(&bytes);
        let expected_host = match agency.short_name.as_str() {
            "Ofcom" => "ofcom.org.uk",
            "NPSA" => "npsa.gov.uk",
            _ => "electoralcommission.org.uk",
        };
        for entry in feed.entries {
            if publishers
                .get(&entry.id)
                .is_some_and(|publisher| !publisher_matches(publisher, expected_host))
            {
                continue;
            }
            let Some(published) = entry.published.or(entry.updated) else {
                continue;
            };
            if published < since || published >= until {
                continue;
            }
            let mut title = entry
                .title
                .map(|x| crate::parse::clean_text(&x.content))
                .unwrap_or_default();
            if agency.short_name == "Ofcom" {
                if !title.contains("www.ofcom.org.uk") {
                    continue;
                }
                title = ofcom_suffix.replace(&title, "").trim().into();
            } else if agency.short_name == "NPSA" {
                title = npsa_suffix.replace(&title, "").trim().into();
            } else {
                title = electoral_suffix.replace(&title, "").trim().into();
                let normalized = title.to_lowercase();
                if ["search criteria", "donation summary", "loan summary"]
                    .iter()
                    .any(|prefix| normalized.starts_with(prefix))
                    || [
                        "home page | electoral commission",
                        "qualifications",
                        "living abroad",
                        "resources for media",
                    ]
                    .contains(&normalized.as_str())
                {
                    continue;
                }
            }
            if title.len() < 12 {
                continue;
            }
            let link = entry
                .links
                .first()
                .map(|x| x.href.clone())
                .unwrap_or_default();
            let host = url::Url::parse(&link).ok().and_then(|url| {
                url.host_str()
                    .map(|host| host.trim_start_matches("www.").to_string())
            });
            if !host
                .as_deref()
                .is_some_and(|host| host == expected_host || host == "news.google.com")
                || uk_news_core::is_agency_homepage(&link, &agency.homepage)
            {
                continue;
            }
            items.push(NewsItem {
                agency: agency.display_name(),
                agency_en: agency.name_en.clone(),
                unit_category: Some(agency.short_name.clone()),
                title,
                link,
                published_at: published,
                summary: entry
                    .summary
                    .map(|x| crate::parse::clean_text(&x.content))
                    .unwrap_or_default(),
                source_feed: source.clone(),
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
                content_type: ContentType::News,
            });
        }
    }
    Ok(crate::parse::dedupe(items))
}

pub(super) fn health_warning(source: &str, items: &[NewsItem], since: DateTime<Utc>) -> String {
    let minimum = match source {
        "BIST" | "DCMS" | "Ofcom" | "Cabinet Office" => 1,
        _ => 0,
    };
    if items.len() < minimum {
        return format!(
            "{source} 筆數異常：取得 {} 筆，低於健康門檻 {minimum} 筆",
            items.len()
        );
    }
    let max_age = match source {
        "BIST" | "DCMS" | "Ofcom" | "Cabinet Office" => Some(14),
        "CMA" | "NCSC" => Some(30),
        "UK IPO" | "ICO" | "Electoral Commission" => Some(45),
        "AISI" | "GDS" | "NPSA" | "UKRI" => Some(60),
        _ => None,
    };
    if since >= Utc::now() - chrono::Duration::days(30) {
        if let (Some(days), Some(newest)) = (max_age, items.iter().map(|x| x.published_at).max()) {
            if newest < Utc::now() - chrono::Duration::days(days) {
                return format!("{source} 最新資料已超過 {days} 天");
            }
        }
    }
    String::new()
}

fn rss_publishers(bytes: &[u8]) -> std::collections::HashMap<String, String> {
    let doc = scraper::Html::parse_document(&String::from_utf8_lossy(bytes));
    let items = scraper::Selector::parse("item").unwrap();
    let guid = scraper::Selector::parse("guid").unwrap();
    let source = scraper::Selector::parse("source[url]").unwrap();
    doc.select(&items)
        .filter_map(|item| {
            let id = item.select(&guid).next()?.text().collect::<String>();
            let publisher = item.select(&source).next()?.value().attr("url")?;
            Some((id.trim().to_string(), publisher.to_string()))
        })
        .collect()
}

fn publisher_matches(publisher: &str, expected_host: &str) -> bool {
    url::Url::parse(publisher).is_ok_and(|url| {
        url.host_str()
            .is_some_and(|host| host.trim_start_matches("www.") == expected_host)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rss_publisher_cannot_spoof_the_official_domain() {
        let xml = br#"<rss><channel><item><guid>article-1</guid><source url="https://www.ofcom.org.uk">Ofcom</source></item><item><guid>article-2</guid><source url="https://ofcom.org.uk.evil.example">Ofcom</source></item></channel></rss>"#;
        let sources = rss_publishers(xml);
        assert!(publisher_matches(&sources["article-1"], "ofcom.org.uk"));
        assert!(!publisher_matches(&sources["article-2"], "ofcom.org.uk"));
        assert!(!publisher_matches(
            "https://third-party.example/ofcom.org.uk",
            "ofcom.org.uk"
        ));
    }
}
