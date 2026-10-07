use super::fallback::{google_news_fallback, health_warning};
use super::*;

pub async fn fetch_agencies(
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    workers: usize,
    selected: &[String],
) -> FetchResult<NewsItem> {
    fetch_agencies_with_progress(since, until, workers, selected, None).await
}

pub async fn fetch_agencies_with_progress(
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    workers: usize,
    selected: &[String],
    progress: Option<SourceProgress>,
) -> FetchResult<NewsItem> {
    let transport = Transport::new();
    let targets = agencies()
        .into_iter()
        .filter(|a| selected.contains(&a.short_name))
        .collect::<Vec<_>>();
    let results = stream::iter(targets)
        .map(|agency| {
            let transport = transport.clone();
            let progress = progress.clone();
            async move {
                let transport = transport.for_source();
                let started = Instant::now();
                let mut items = vec![];
                let mut warnings = vec![];
                let mut successes = 0usize;
                let mut candidate_count = 0usize;
                let mut observations = vec![];
                let mut precise_out_of_period_links = std::collections::HashSet::new();
                if crate::catalog::uses_govuk_search(&agency.short_name) {
                    let slug = agency.short_name.strip_prefix("govuk:").unwrap();
                    match fetch_govuk_search(
                        &transport,
                        &agency,
                        slug,
                        since,
                        until,
                        &mut observations,
                    )
                    .await
                    {
                        Ok((mut found, warning, candidates)) => {
                            candidate_count += candidates;
                            successes += 1;
                            items.append(&mut found);
                            if let Some(warning) = warning {
                                warnings.push(format!("{} {warning}", agency.short_name));
                            }
                        }
                        Err(error) => {
                            warnings.push(format!("{} GOV.UK 搜尋失敗：{error}", agency.short_name))
                        }
                    }
                } else {
                    for source in &agency.feeds {
                        match transport
                            .bytes(transport.get(source), &mut observations)
                            .await
                        {
                            Ok(b) => {
                                let mut feed_candidates = 0usize;
                                if let Ok(feed) = crate::parse::parse_feed_with_dates(&b[..]) {
                                    collect_out_of_period_links(
                                        &feed,
                                        since,
                                        until,
                                        &mut precise_out_of_period_links,
                                    );
                                    feed_candidates = feed
                                        .entries
                                        .iter()
                                        .filter(|entry| {
                                            let in_period = entry
                                                .published
                                                .or(entry.updated)
                                                .is_none_or(|date| date >= since && date < until);
                                            let allowed_link =
                                                entry.links.first().is_none_or(|link| {
                                                    !uk_news_core::is_agency_homepage(&link.href, &agency.homepage)
                                                        && (agency.link_include_patterns.is_empty()
                                                        || agency.link_include_patterns.iter().any(
                                                            |pattern| link.href.contains(pattern),
                                                        ))
                                                });
                                            in_period && allowed_link
                                        })
                                        .count();
                                    candidate_count += feed_candidates;
                                    if agency.short_name.starts_with("court-")
                                        || crate::catalog::is_catalog_feed(&agency.short_name)
                                    {
                                        let oldest = feed
                                            .entries
                                            .iter()
                                            .filter_map(|entry| entry.published.or(entry.updated))
                                            .min();
                                        if oldest.is_some_and(|date| date > since) {
                                            warnings.push(format!(
                                                "{} 官方 RSS 最舊資料晚於查詢起日，期間可能不完整",
                                                agency.short_name
                                            ));
                                        }
                                    }
                                }
                                match parse_feed_document(&b, &agency, source, since, until) {
                                    Ok(mut x) => {
                                        if feed_candidates > 0 && x.is_empty() {
                                            warnings.push(format!(
                                                "{} RSS 有候選資料但解析為零筆",
                                                agency.short_name
                                            ));
                                        }
                                        successes += 1;
                                        items.append(&mut x)
                                    }
                                    Err(e) => warnings
                                        .push(format!("{} RSS 解析失敗：{}", agency.short_name, e)),
                                }
                            }
                            Err(e) => {
                                warnings.push(format!("{} RSS 讀取失敗：{}", agency.short_name, e))
                            }
                        }
                    }
                    let fetch_news_pages = items.is_empty();
                    for source in agency
                        .news_pages
                        .iter()
                        .filter(|_| fetch_news_pages)
                        .chain(agency.official_pages.iter())
                    {
                        match transport
                            .bytes(transport.get(source), &mut observations)
                            .await
                        {
                            Ok(b) => {
                                successes += 1;
                                let html = String::from_utf8_lossy(&b);
                                let catalog_html =
                                    crate::catalog::is_catalog_html(&agency.short_name);
                                let mut parsed = if catalog_html {
                                    crate::parse_catalog_news_index(
                                        &html, &agency, source, since, until,
                                    )
                                } else {
                                    parse_official_html(&html, &agency, source, since, until)
                                };
                                if catalog_html {
                                    let all_dated = crate::parse_catalog_news_index(
                                        &html,
                                        &agency,
                                        source,
                                        NaiveDate::from_ymd_opt(1990, 1, 1)
                                            .unwrap()
                                            .and_hms_opt(0, 0, 0)
                                            .unwrap()
                                            .and_utc(),
                                        DateTime::<Utc>::MAX_UTC,
                                    );
                                    if all_dated
                                        .iter()
                                        .map(|item| item.published_at)
                                        .min()
                                        .is_some_and(|date| date > since)
                                    {
                                        warnings.push(format!(
                                            "{} 官方列表最舊資料晚於查詢起日，期間可能不完整",
                                            agency.short_name
                                        ));
                                    }
                                    if all_dated.is_empty() {
                                        warnings.push(format!(
                                            "{} 官方列表未解析到有日期的資料，請確認頁面格式",
                                            agency.short_name
                                        ));
                                    }
                                }
                                exclude_precise_out_of_period_links(
                                    &mut parsed,
                                    &precise_out_of_period_links,
                                );
                                let candidate_date = if uk_news_core::is_agency_homepage(source, &agency.homepage) {
                                    Html::parse_document(&html).select(&Selector::parse("article, li, .search-result, .card").unwrap()).any(|node| page_has_in_range_date(&node.html(), since, until))
                                } else { page_has_in_range_date(&html, since, until) };
                                if parsed.is_empty() && candidate_date
                                {
                                    candidate_count += 1;
                                    warnings.push(format!(
                                        "{} 官方頁有期間內日期但解析為零筆",
                                        agency.short_name
                                    ));
                                }
                                candidate_count += parsed.len();
                                items.extend(parsed);
                            }
                            Err(e) => warnings
                                .push(format!("{} 官方頁讀取失敗：{}", agency.short_name, e)),
                        }
                    }
                }
                if items.is_empty()
                    && matches!(
                        agency.short_name.as_str(),
                        "Ofcom" | "NPSA" | "Electoral Commission"
                    )
                {
                    match google_news_fallback(&transport, &agency, since, until, &mut observations)
                        .await
                    {
                        Ok(mut fallback) => {
                            successes += 1;
                            if !fallback.is_empty() { warnings.push(format!("{} 使用 Google News 備援；日期取自備援 RSS，未核對官方發布日期", agency.short_name)); }
                            items.append(&mut fallback);
                        }
                        Err(error) => warnings.push(format!(
                            "{} Google News 備援讀取失敗：{error}",
                            agency.short_name
                        )),
                    }
                }
                items.retain(|item| !uk_news_core::is_agency_homepage(&item.link, &agency.homepage));
                items = crate::parse::dedupe(items);
                let success = successes > 0;
                let mut warning = warnings.join("；");
                if warning.is_empty() {
                    warning = health_warning(&agency.short_name, &items, since);
                }
                let newest = items
                    .iter()
                    .map(|x| x.published_at)
                    .max()
                    .map(|x| x.to_rfc3339())
                    .unwrap_or_default();
                let health = SourceHealth {
                    source: agency.short_name.clone(),
                    critical: true,
                    success,
                    item_count: items.len(),
                    duration_seconds: round_duration(started.elapsed().as_secs_f64()),
                    newest_published_at: newest,
                    warning: warning.clone(),
                    candidate_count,
                    parser_version: "v1".into(),
                    fetched_at: observations
                        .last()
                        .map(|observation| observation.fetched_at.clone())
                        .unwrap_or_else(|| Utc::now().to_rfc3339()),
                    endpoints: observations,
                };
                if let Some(progress) = progress {
                    progress(&health);
                }
                (items, health, warnings)
            }
        })
        .buffer_unordered(workers.max(1))
        .collect::<Vec<_>>()
        .await;
    let mut items = vec![];
    let mut health = vec![];
    let mut warnings = vec![];
    for (mut i, h, mut w) in results {
        items.append(&mut i);
        health.push(h);
        warnings.append(&mut w)
    }
    health.sort_by(|a, b| a.source.cmp(&b.source));
    items = crate::parse::dedupe(items);
    FetchResult {
        items,
        health,
        warnings,
    }
}

async fn fetch_govuk_search(
    transport: &Transport,
    agency: &Agency,
    slug: &str,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    observations: &mut Vec<EndpointObservation>,
) -> Result<(Vec<NewsItem>, Option<String>, usize), String> {
    let mut items = Vec::new();
    let mut start = 0usize;
    let mut candidate_count = 0usize;
    let mut malformed_count = 0usize;
    for _ in 0..50 {
        let date_filter = format!("from:{},to:{}", since.date_naive(), until.date_naive());
        let query = [
            ("filter_organisations", slug.to_string()),
            ("filter_public_timestamp", date_filter),
            (
                "fields",
                "title,link,description,public_timestamp,format".into(),
            ),
            ("order", "-public_timestamp".into()),
            ("count", "100".into()),
            ("start", start.to_string()),
        ];
        let builder = transport
            .get("https://www.gov.uk/api/search.json")
            .query(&query);
        let source_url = builder
            .try_clone()
            .ok_or("GOV.UK query cannot be cloned")?
            .build()
            .map_err(|error| error.to_string())?
            .url()
            .to_string();
        let bytes = match transport.bytes(builder, observations).await {
            Ok(bytes) => bytes,
            Err(error) if !items.is_empty() => {
                return Ok((
                    crate::parse::dedupe(items),
                    Some(format!("搜尋分頁中斷，已保留取得的資料：{error}")),
                    candidate_count,
                ));
            }
            Err(error) => return Err(error),
        };
        let payload: Value = match serde_json::from_slice(&bytes) {
            Ok(payload) => payload,
            Err(error) if !items.is_empty() => {
                return Ok((
                    crate::parse::dedupe(items),
                    Some(format!("搜尋分頁格式異常，已保留取得的資料：{error}")),
                    candidate_count,
                ));
            }
            Err(error) => return Err(error.to_string()),
        };
        let Some(results) = payload.get("results").and_then(Value::as_array) else {
            if !items.is_empty() {
                return Ok((
                    crate::parse::dedupe(items),
                    Some("搜尋分頁缺少 results，已保留取得的資料".into()),
                    candidate_count,
                ));
            }
            return Err("GOV.UK 搜尋缺少 results".into());
        };
        for value in results {
            let Some(path) = value.get("link").and_then(Value::as_str) else {
                malformed_count += 1;
                continue;
            };
            let link = if path.starts_with("https://") {
                path.to_string()
            } else {
                format!("https://www.gov.uk{path}")
            };
            if uk_news_core::is_agency_homepage(&link, &agency.homepage) {
                continue;
            }
            let document_format = value
                .get("format")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_lowercase();
            let is_decision = is_decision_format(&document_format);
            let allowed_path = agency
                .link_include_patterns
                .iter()
                .any(|pattern| link.contains(pattern));
            let official_decision = is_decision && is_govuk_host(&link);
            if !allowed_path && !official_decision {
                continue;
            }
            let Some(raw_date) = value.get("public_timestamp").and_then(Value::as_str) else {
                malformed_count += 1;
                continue;
            };
            let Ok(published_at) = DateTime::parse_from_rfc3339(raw_date) else {
                malformed_count += 1;
                continue;
            };
            let published_at = published_at.with_timezone(&Utc);
            if published_at < since || published_at >= until {
                continue;
            }
            candidate_count += 1;
            let title = value
                .get("title")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim();
            if title.is_empty() {
                malformed_count += 1;
                continue;
            }
            let summary = value
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("");
            items.push(NewsItem {
                agency: agency.display_name(),
                agency_en: agency.name_en.clone(),
                unit_category: Some(agency.short_name.clone()),
                title: crate::parse::clean_text(title),
                link: link.clone(),
                published_at,
                summary: crate::parse::clean_text(summary),
                source_feed: source_url.clone(),
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
                content_type: if is_decision {
                    ContentType::Judgment
                } else {
                    content_type_for_link(&link, title, "")
                },
            });
        }
        start += results.len();
        if results.is_empty()
            || start
                >= payload
                    .get("total")
                    .and_then(Value::as_u64)
                    .unwrap_or(start as u64) as usize
        {
            let mut warning_parts = Vec::new();
            if malformed_count > 0 {
                warning_parts.push(format!("搜尋有 {malformed_count} 筆資料欄位不完整"));
            }
            if candidate_count > 0 && items.is_empty() {
                warning_parts.push("搜尋有候選資料但解析為零筆".into());
            }
            let warning = (!warning_parts.is_empty()).then(|| warning_parts.join("；"));
            return Ok((crate::parse::dedupe(items), warning, candidate_count));
        }
    }
    Ok((
        crate::parse::dedupe(items),
        Some("搜尋結果超過 5000 筆，請縮短期間".into()),
        candidate_count,
    ))
}

fn is_govuk_host(link: &str) -> bool {
    url::Url::parse(link)
        .ok()
        .and_then(|value| value.host_str().map(str::to_owned))
        .is_some_and(|host| host == "www.gov.uk" || host == "gov.uk")
}

fn is_decision_format(value: &str) -> bool {
    value.contains("decision") || value.contains("judgment")
}

#[cfg(test)]
mod selection_tests {
    use super::*;
    use chrono::TimeZone;

    #[test]
    fn dated_page_with_no_parsed_records_is_a_candidate() {
        let since = Utc.with_ymd_and_hms(2026, 9, 22, 16, 0, 0).unwrap();
        let until = Utc.with_ymd_and_hms(2026, 9, 23, 16, 0, 0).unwrap();
        assert!(page_has_in_range_date(
            "<html><time datetime='2026-09-23'>23 September</time></html>",
            since,
            until,
        ));
        assert!(!page_has_in_range_date(
            "<html><time datetime='2026-09-21'>21 September</time></html>",
            since,
            until,
        ));
    }

    #[test]
    fn precise_feed_date_excludes_ambiguous_html_day() {
        let since = Utc.with_ymd_and_hms(2026, 9, 22, 16, 0, 0).unwrap();
        let until = Utc.with_ymd_and_hms(2026, 9, 23, 16, 0, 0).unwrap();
        let link = "https://www.gov.uk/government/news/test-ai-appointment";
        let feed = format!(
            "<feed xmlns='http://www.w3.org/2005/Atom'><id>test</id><title>test</title><updated>2026-09-23T16:00:01Z</updated><entry><id>{link}</id><title>Test AI appointment</title><updated>2026-09-23T16:00:01Z</updated><link href='{link}' /></entry></feed>"
        );
        let parsed_feed = parser::parse(feed.as_bytes()).unwrap();
        let mut excluded = HashSet::new();
        collect_out_of_period_links(&parsed_feed, since, until, &mut excluded);
        let agency = agencies()
            .into_iter()
            .find(|agency| agency.short_name == "Cabinet Office")
            .unwrap();
        let html = format!(
            "<ul><li><a href='{link}'>Test AI appointment</a><time datetime='2026-09-23'>23 September</time></li></ul>"
        );
        let mut items = parse_official_html(&html, &agency, &agency.homepage, since, until);
        assert_eq!(items.len(), 1);
        exclude_precise_out_of_period_links(&mut items, &excluded);
        assert!(items.is_empty());
    }

    #[tokio::test]
    async fn empty_selection_does_not_fetch_entire_catalog() {
        let now = Utc::now();
        let result = fetch_agencies(now, now, 6, &[]).await;
        assert!(result.items.is_empty());
        assert!(result.health.is_empty());
    }

    #[test]
    fn tribunal_decision_paths_are_eligible_only_on_govuk() {
        assert!(is_decision_format("utaac_decision"));
        assert!(is_govuk_host(
            "https://www.gov.uk/administrative-appeals-tribunal-decisions/test"
        ));
        assert!(!is_govuk_host(
            "https://elsewhere.example/administrative-appeals-tribunal-decisions/test"
        ));
    }
}
