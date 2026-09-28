use super::*;

async fn fetch_parliament_api(
    transport: &Transport,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
    observations: &mut Vec<EndpointObservation>,
) -> Result<Vec<ParliamentBriefing>, String> {
    let mut output = vec![];
    for page in 0..20 {
        let bytes = transport
            .bytes(
                transport
                    .get("https://lda.data.parliament.uk/researchbriefings.json")
                    .query(&[
                        ("_view", "all"),
                        ("_page", &page.to_string()),
                        ("_pageSize", "500"),
                        ("_sort", "-date"),
                    ]),
                observations,
            )
            .await?;
        let payload: Value = serde_json::from_slice(&bytes).map_err(|error| error.to_string())?;
        let values = payload
            .pointer("/result/items")
            .and_then(Value::as_array)
            .ok_or("API payload 缺少 result.items")?;
        let mut oldest = None;
        for value in values {
            let Some(published_at) = first_value(value, &["date", "published", "publicationDate"])
                .and_then(|text| parse_api_date(&text))
            else {
                continue;
            };
            oldest =
                Some(oldest.map_or(published_at, |date: DateTime<Utc>| date.min(published_at)));
            if published_at < since || published_at >= until {
                continue;
            }
            let publisher =
                first_value(value, &["publisher", "publisher_label"]).unwrap_or_default();
            let title = first_value(value, &["title", "label"]).unwrap_or_default();
            let webpage_url =
                first_value(value, &["_about", "url", "webpage", "uri"]).unwrap_or_default();
            if publisher.is_empty() || title.is_empty() || webpage_url.is_empty() {
                continue;
            }
            let chamber = match publisher.as_str() {
                "House of Commons Library" => "House of Commons",
                "House of Lords Library" => "House of Lords",
                "Parliamentary Office of Science and Technology" => "POST",
                _ => "",
            };
            let combined = format!("{title} {webpage_url}");
            let id =
                first_value(value, &["identifier", "id"]).unwrap_or_else(|| identifier(&combined));
            output.push(ParliamentBriefing {
                published_at,
                chamber: chamber.into(),
                publisher,
                title,
                summary: first_value(value, &["abstract", "description", "summary"])
                    .unwrap_or_default(),
                identifier: id.clone(),
                webpage_url,
                pdf_url: first_value(value, &["pdf", "pdfUrl", "attachment", "document"])
                    .unwrap_or_else(|| pdf_url(&combined, &id)),
                topics: value
                    .get("topic")
                    .or_else(|| value.get("topics"))
                    .map(value_list)
                    .unwrap_or_default(),
                document_type: first_value(value, &["type", "publicationType"])
                    .unwrap_or_else(|| "Research Briefing".into()),
                fetched_from: "Research Briefings API".into(),
                matched_topics: vec![],
                matched_keywords: vec![],
                title_matched_keywords: vec![],
                summary_matched_keywords: vec![],
                core_matched_keywords: vec![],
                general_matched_keywords: vec![],
                supporting_matched_keywords: vec![],
                relevance_score: 0,
                relevance_level: String::new(),
            });
        }
        if values.len() < 500 || oldest.is_some_and(|date| date < since) {
            break;
        }
    }
    Ok(dedupe_parliament(output))
}

fn first_value(value: &Value, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| {
        value.get(*key).and_then(value_text).or_else(|| {
            value
                .pointer(&format!("/{}", key.replace('.', "/")))
                .and_then(value_text)
        })
    })
}

fn value_text(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.clone()),
        Value::Number(number) => Some(number.to_string()),
        Value::Array(values) => values.iter().find_map(value_text),
        Value::Object(map) => map
            .get("_value")
            .or_else(|| map.get("value"))
            .or_else(|| map.get("label"))
            .and_then(value_text),
        _ => None,
    }
}

fn value_list(value: &Value) -> Vec<String> {
    match value {
        Value::Array(values) => values.iter().filter_map(value_text).collect(),
        _ => value_text(value).into_iter().collect(),
    }
}

fn parse_api_date(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|date| date.with_timezone(&Utc))
        .or_else(|| {
            chrono::NaiveDate::parse_from_str(value, "%Y-%m-%d")
                .ok()
                .and_then(|date| date.and_hms_opt(0, 0, 0))
                .map(|date| date.and_utc())
        })
}
pub async fn fetch_parliament(
    since: DateTime<Utc>,
    until: DateTime<Utc>,
) -> FetchResult<ParliamentBriefing> {
    let transport = Transport::new();
    let feeds = [
        (
            "House of Commons Library",
            "House of Commons",
            "https://commonslibrary.parliament.uk/research-briefings/feed/",
        ),
        (
            "House of Lords Library",
            "House of Lords",
            "https://lordslibrary.parliament.uk/research-briefings/feed/",
        ),
        (
            "Parliamentary Office of Science and Technology",
            "POST",
            "https://post.parliament.uk/feed/",
        ),
    ];
    let mut items = vec![];
    let mut health = vec![];
    let mut warnings = vec![];
    if std::env::var("UK_PARLIAMENT_TRY_API").as_deref() == Ok("1") {
        let started = Instant::now();
        let mut observations = vec![];
        match fetch_parliament_api(&transport, since, until, &mut observations).await {
            Ok(mut api_items) if !api_items.is_empty() => {
                let newest = api_items
                    .iter()
                    .map(|item| item.published_at)
                    .max()
                    .map(|value| value.to_rfc3339())
                    .unwrap_or_default();
                health.push(SourceHealth {
                    source: "Research Briefings API".into(),
                    critical: false,
                    success: true,
                    item_count: api_items.len(),
                    duration_seconds: round_duration(started.elapsed().as_secs_f64()),
                    newest_published_at: newest,
                    warning: String::new(),
                    candidate_count: api_items.len(),
                    parser_version: "v1".into(),
                    fetched_at: last_fetched_at(&observations),
                    endpoints: observations,
                });
                items.append(&mut api_items);
            }
            Ok(_) => {
                let warning =
                    "Research Briefings API 未回傳指定期間資料，繼續使用官方 RSS".to_string();
                health.push(SourceHealth {
                    source: "Research Briefings API".into(),
                    critical: false,
                    success: false,
                    item_count: 0,
                    duration_seconds: round_duration(started.elapsed().as_secs_f64()),
                    newest_published_at: String::new(),
                    warning: warning.clone(),
                    candidate_count: 0,
                    parser_version: "v1".into(),
                    fetched_at: last_fetched_at(&observations),
                    endpoints: observations,
                });
                warnings.push(warning);
            }
            Err(error) => {
                let warning = format!("Research Briefings API 無法使用，繼續使用官方 RSS：{error}");
                health.push(SourceHealth {
                    source: "Research Briefings API".into(),
                    critical: false,
                    success: false,
                    item_count: 0,
                    duration_seconds: round_duration(started.elapsed().as_secs_f64()),
                    newest_published_at: String::new(),
                    warning: warning.clone(),
                    candidate_count: 0,
                    parser_version: "v1".into(),
                    fetched_at: last_fetched_at(&observations),
                    endpoints: observations,
                });
                warnings.push(warning);
            }
        }
    }
    for (publisher, chamber, url) in feeds {
        let started = Instant::now();
        let mut source_items = vec![];
        let mut error = None;
        let mut observations = vec![];
        let mut candidate_count = 0usize;
        for page in 1..=20 {
            let page_url = if page == 1 {
                url.into()
            } else {
                format!("{url}?paged={page}")
            };
            let bytes = match transport
                .bytes(transport.get(&page_url), &mut observations)
                .await
            {
                Ok(bytes) => bytes,
                Err(e) => {
                    error = Some(e);
                    break;
                }
            };
            let feed = match parser::parse(&bytes[..]) {
                Ok(f) => f,
                Err(e) => {
                    error = Some(e.to_string());
                    break;
                }
            };
            let entry_count = feed.entries.len();
            candidate_count += feed
                .entries
                .iter()
                .filter(|entry| {
                    entry
                        .published
                        .or(entry.updated)
                        .is_none_or(|date| date >= since && date < until)
                })
                .count();
            let mut oldest = None;
            for entry in feed.entries {
                let Some(published) = entry.published.or(entry.updated) else {
                    continue;
                };
                oldest = Some(oldest.map_or(published, |x: DateTime<Utc>| x.min(published)));
                if published < since || published >= until {
                    continue;
                }
                let title = entry
                    .title
                    .map(|x| crate::parse::clean_text(&x.content))
                    .unwrap_or_default();
                let webpage_url = entry
                    .links
                    .first()
                    .map(|x| x.href.clone())
                    .unwrap_or_default();
                if title.trim().is_empty() || webpage_url.is_empty() {
                    continue;
                }
                let summary = entry
                    .summary
                    .map(|x| strip_html(&x.content))
                    .unwrap_or_default();
                let content = entry
                    .content
                    .as_ref()
                    .and_then(|value| value.body.as_deref())
                    .unwrap_or_default();
                let combined = format!("{} {} {}", title, webpage_url, summary);
                let identifier = identifier(&combined);
                let pdf_url = pdf_url(content, &identifier);
                let topics = entry.categories.into_iter().map(|x| x.term).collect();
                source_items.push(ParliamentBriefing {
                    published_at: published,
                    chamber: chamber.into(),
                    publisher: publisher.into(),
                    title: title.trim().into(),
                    summary,
                    identifier,
                    webpage_url,
                    pdf_url,
                    topics,
                    document_type: "Research Briefing".into(),
                    fetched_from: format!("Official RSS: {url}"),
                    matched_topics: vec![],
                    matched_keywords: vec![],
                    title_matched_keywords: vec![],
                    summary_matched_keywords: vec![],
                    core_matched_keywords: vec![],
                    general_matched_keywords: vec![],
                    supporting_matched_keywords: vec![],
                    relevance_score: 0,
                    relevance_level: String::new(),
                });
            }
            if entry_count < 10 || oldest.is_some_and(|x| x < since) {
                break;
            }
        }
        let success = error.is_none();
        let mut warning = error
            .map(|e| format!("{publisher} RSS 讀取失敗：{e}"))
            .unwrap_or_default();
        if candidate_count > 0 && source_items.is_empty() && warning.is_empty() {
            warning = format!("{publisher} RSS 有候選資料但解析為零筆");
        }
        if !warning.is_empty() {
            warnings.push(warning.clone())
        }
        source_items = dedupe_parliament(source_items);
        let newest = source_items
            .iter()
            .map(|x| x.published_at)
            .max()
            .map(|x| x.to_rfc3339())
            .unwrap_or_default();
        health.push(SourceHealth {
            source: format!("{publisher} RSS"),
            critical: true,
            success,
            item_count: source_items.len(),
            duration_seconds: round_duration(started.elapsed().as_secs_f64()),
            newest_published_at: newest,
            warning,
            candidate_count: source_items.len(),
            parser_version: "v1".into(),
            fetched_at: last_fetched_at(&observations),
            endpoints: observations,
        });
        items.append(&mut source_items)
    }
    let archives=[("House of Lords Library Science & Technology","House of Lords Library","House of Lords","https://lordslibrary.parliament.uk/topic/science-environment/science-environment-science-technology/"),("House of Commons Library Technology","House of Commons Library","House of Commons","https://commonslibrary.parliament.uk/topic/science/technology/"),("House of Commons Library Sciences","House of Commons Library","House of Commons","https://commonslibrary.parliament.uk/topic/science/sciences/")];
    for (label, publisher, chamber, url) in archives {
        let started = Instant::now();
        let mut source_items = vec![];
        let mut warning = String::new();
        let mut observations = vec![];
        match transport.bytes(transport.get(url), &mut observations).await {
            Ok(bytes) => {
                source_items = parse_topic_archive(
                    &String::from_utf8_lossy(&bytes),
                    url,
                    publisher,
                    chamber,
                    since,
                    until,
                )
            }
            Err(e) => warning = format!("{label} 主題頁讀取失敗：{e}"),
        };
        let success = warning.is_empty();
        if !success {
            warnings.push(warning.clone())
        }
        let newest = source_items
            .iter()
            .map(|x| x.published_at)
            .max()
            .map(|x| x.to_rfc3339())
            .unwrap_or_default();
        health.push(SourceHealth {
            source: format!("{label} topic archive"),
            critical: false,
            success,
            item_count: source_items.len(),
            duration_seconds: round_duration(started.elapsed().as_secs_f64()),
            newest_published_at: newest,
            warning,
            candidate_count: source_items.len(),
            parser_version: "v1".into(),
            fetched_at: last_fetched_at(&observations),
            endpoints: observations,
        });
        items.append(&mut source_items)
    }
    FetchResult {
        items: dedupe_parliament(items),
        health,
        warnings,
    }
}

fn strip_html(text: &str) -> String {
    crate::parse::clean_text(text)
}
fn identifier(text: &str) -> String {
    Regex::new(r"(?i)\b(?:CBP|SN|LLN|POST-PN|POSTNOTE|POSTBRIEF)-?\d+\b")
        .unwrap()
        .find(text)
        .map(|x| x.as_str().to_uppercase())
        .unwrap_or_default()
}
fn pdf_url(text: &str, id: &str) -> String {
    if id.is_empty() {
        return String::new();
    }
    for found in Regex::new(r#"(?i)https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]*)?"#)
        .unwrap()
        .find_iter(text)
    {
        if found.as_str().to_lowercase().contains(&id.to_lowercase()) {
            return found.as_str().into();
        }
    }
    if id.starts_with("CBP-") || id.starts_with("SN-") {
        format!("https://researchbriefings.files.parliament.uk/documents/{id}/{id}.pdf")
    } else {
        String::new()
    }
}
fn parse_topic_archive(
    html: &str,
    base: &str,
    publisher: &str,
    chamber: &str,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
) -> Vec<ParliamentBriefing> {
    let doc = Html::parse_document(html);
    let card = Selector::parse("article.card").unwrap();
    let link = Selector::parse(".card__heading a[href], h2 a[href], h3 a[href]").unwrap();
    let time = Selector::parse("time[datetime]").unwrap();
    let tag = Selector::parse(".tag-list a[href]").unwrap();
    let base_url = url::Url::parse(base).ok();
    let mut out = vec![];
    for c in doc.select(&card) {
        let (Some(a), Some(t)) = (c.select(&link).next(), c.select(&time).next()) else {
            continue;
        };
        let Some(published) = t
            .value()
            .attr("datetime")
            .and_then(|x| DateTime::parse_from_rfc3339(x).ok())
            .map(|x| x.with_timezone(&Utc))
        else {
            continue;
        };
        if published < since || published >= until {
            continue;
        }
        let title = a.text().collect::<Vec<_>>().join(" ").trim().to_string();
        let href = a.value().attr("href").unwrap_or("");
        let webpage_url = base_url
            .as_ref()
            .and_then(|x| x.join(href).ok())
            .map(|x| x.to_string())
            .unwrap_or_else(|| href.into());
        let combined = format!("{title} {webpage_url}");
        let id = identifier(&combined);
        let topics = c
            .select(&tag)
            .map(|x| x.text().collect::<Vec<_>>().join(" ").trim().into())
            .collect();
        out.push(ParliamentBriefing {
            published_at: published,
            chamber: chamber.into(),
            publisher: publisher.into(),
            title,
            summary: String::new(),
            identifier: id.clone(),
            webpage_url,
            pdf_url: pdf_url(&combined, &id),
            topics,
            document_type: "Research Briefing".into(),
            fetched_from: format!("Official topic archive: {base}"),
            matched_topics: vec![],
            matched_keywords: vec![],
            title_matched_keywords: vec![],
            summary_matched_keywords: vec![],
            core_matched_keywords: vec![],
            general_matched_keywords: vec![],
            supporting_matched_keywords: vec![],
            relevance_score: 0,
            relevance_level: String::new(),
        })
    }
    dedupe_parliament(out)
}
fn dedupe_parliament(mut items: Vec<ParliamentBriefing>) -> Vec<ParliamentBriefing> {
    items.sort_by_key(|x| std::cmp::Reverse(x.published_at));
    let mut seen = HashSet::new();
    items
        .into_iter()
        .filter(|x| {
            seen.insert(if !x.identifier.is_empty() {
                x.identifier.clone()
            } else if !x.webpage_url.is_empty() {
                x.webpage_url.trim_end_matches('/').into()
            } else {
                format!("{}:{}", x.publisher, x.title)
            })
        })
        .collect()
}
