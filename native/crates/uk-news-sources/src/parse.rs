use anyhow::{anyhow, Result};
use chrono::{DateTime, NaiveDate, NaiveDateTime, Utc};
use feed_rs::parser;
use scraper::{Html, Selector};
use serde_json::Value;
use uk_news_core::{is_agency_homepage, Agency, ContentType, NewsItem};
use url::Url;

pub(crate) fn clean_text(value: &str) -> String {
    let doc = Html::parse_fragment(value);
    let text = doc.root_element().text().collect::<Vec<_>>().join(" ");
    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let apostrophe = regex::Regex::new(r"(?P<a>[A-Za-z])[’‘](?P<b>[A-Za-z])").unwrap();
    apostrophe.replace_all(&text, "$a'$b").into_owned()
}

pub fn content_type_for_link(link: &str, title: &str, context: &str) -> ContentType {
    let text = format!("{link} {title} {context}").to_lowercase();
    let path = Url::parse(link)
        .ok()
        .map(|value| value.path().to_lowercase())
        .unwrap_or_default();
    if path.contains("/judgment") || path.contains("/judicial-decision") {
        ContentType::Judgment
    } else if path.contains("/guidance/")
        || path.contains("/collection/")
        || text.contains("guidance")
    {
        ContentType::Guidance
    } else if path.contains("/report")
        || path.contains("/research/")
        || text.contains("report")
        || text.contains("research")
    {
        ContentType::Report
    } else if path.contains("/publication")
        || path.contains("/consultation")
        || text.contains("publication")
        || text.contains("consultation")
    {
        ContentType::Publication
    } else {
        ContentType::News
    }
}

fn allowed(agency: &Agency, link: &str) -> bool {
    if is_agency_homepage(link, &agency.homepage) {
        return false;
    }
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

// Preserve feed-rs standard date handling, supplementing only missing timestamps.
pub(crate) fn parse_feed_with_dates(bytes: &[u8]) -> Result<feed_rs::model::Feed> {
    let mut feed = parser::parse(bytes)?;
    if feed
        .entries
        .iter()
        .any(|entry| entry.published.is_none() && entry.updated.is_none())
    {
        let supplemental = parser::Builder::new()
            .timestamp_parser(parse_date)
            .build()
            .parse(bytes)?;
        for (entry, dated) in feed.entries.iter_mut().zip(supplemental.entries) {
            if entry.id == dated.id {
                entry.published = entry.published.or(dated.published);
                entry.updated = entry.updated.or(dated.updated);
            }
        }
    }
    Ok(feed)
}

pub fn parse_feed_document(
    bytes: &[u8],
    agency: &Agency,
    source: &str,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
) -> Result<Vec<NewsItem>> {
    let feed = parse_feed_with_dates(bytes)?;
    let atom = feed.feed_type == feed_rs::model::FeedType::Atom;
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
            .map(|x| {
                // Atom text constructs explicitly distinguish literal text from HTML.
                // RSS titles lack that distinction and may contain escaped markup.
                if atom && x.content_type.as_str() == "text/plain" {
                    clean_text(
                        &x.content
                            .replace('&', "&amp;")
                            .replace('<', "&lt;")
                            .replace('>', "&gt;"),
                    )
                } else {
                    clean_text(&x.content)
                }
            })
            .unwrap_or_default();
        let link = entry
            .links
            .first()
            .map(|x| x.href.clone())
            .unwrap_or_default();
        if title.is_empty() || link.is_empty() || !allowed(agency, &link) {
            continue;
        }
        let summary = entry
            .summary
            .filter(|summary| !summary.content.is_empty())
            .map(|x| clean_text(&x.content))
            .or_else(|| {
                entry
                    .content
                    .and_then(|content| content.body)
                    .map(|body| clean_text(&body))
            })
            .unwrap_or_default();
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
            content_type: if agency.short_name.ends_with(":judgments") {
                ContentType::Judgment
            } else {
                content_type_for_link(&link, &title, "")
            },
        });
    }
    Ok(out)
}

fn parse_date(text: &str) -> Option<DateTime<Utc>> {
    let normalized = text
        .split_whitespace()
        .map(|token| if token == "Sept" { "Sep" } else { token })
        .collect::<Vec<_>>()
        .join(" ");
    static SLASH: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let slash = SLASH.get_or_init(|| regex::Regex::new(r"\s*/\s*").unwrap());
    let normalized = slash.replace_all(&normalized, "/");
    let text = normalized.as_ref();
    static ORDINAL: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let ordinal =
        ORDINAL.get_or_init(|| regex::Regex::new(r"^(\d{1,2})(?:st|nd|rd|th)(\s)").unwrap());
    let normalized = ordinal.replace(text.trim(), "$1$2");
    let text = normalized.as_ref();
    DateTime::parse_from_rfc3339(text)
        .ok()
        .map(|x| x.with_timezone(&Utc))
        .or_else(|| {
            DateTime::parse_from_rfc2822(text)
                .ok()
                .map(|x| x.with_timezone(&Utc))
        })
        .or_else(|| {
            [
                "%Y-%m-%dT%H:%MZ",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M",
            ]
            .iter()
            .find_map(|format| NaiveDateTime::parse_from_str(text.trim(), format).ok())
            .map(|value| value.and_utc())
        })
        .or_else(|| {
            ["%d %B %Y", "%B %d, %Y", "%d %b %Y", "%d %b, %Y", "%d/%m/%Y"]
                .iter()
                .find_map(|format| NaiveDate::parse_from_str(text.trim(), format).ok())
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

#[test]
fn reviewed_index_fields_bind_date_and_headline_to_the_same_card() {
    let html = include_str!("../../../../tests/fixtures/catalog_reviewed_indexes.html");
    for (host, expected, day) in [
        ("www.ombudsman.wales", "ombudsman", "29"),
        ("www.uksbs.co.uk", "business", "28"),
        ("www.oscr.org.uk", "charity", "29"),
        ("www.foi.scot", "foi", "25"),
        ("www.pirc.scot", "pirc", "26"),
    ] {
        let page = format!("https://{host}/news");
        let agency = Agency {
            name_zh: "Official".into(),
            name_en: "Official".into(),
            short_name: "catalog:test".into(),
            homepage: page.clone(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let items = parse_catalog_news_index(
            html,
            &agency,
            &page,
            parse_date("2026-09-20").unwrap(),
            parse_date("2026-09-30").unwrap(),
        );
        assert_eq!(items.len(), 1, "{host}");
        assert!(items[0].link.ends_with(expected));
        assert_eq!(items[0].published_at.format("%d").to_string(), day);
    }
}

#[test]
fn shared_publisher_rules_require_an_explicit_body_scoped_index() {
    let html = include_str!("../../../../tests/fixtures/catalog_reviewed_indexes.html");
    for (host, path, expected) in [
        (
            "www.ukri.org",
            "/councils/research-england/news/",
            "research-england",
        ),
        ("audit.scot", "/accounts-commission", "accounts"),
    ] {
        let page = format!("https://{host}{path}");
        let agency = Agency {
            name_zh: "Official".into(),
            name_en: "Official".into(),
            short_name: "catalog:test".into(),
            homepage: page.clone(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let items = parse_catalog_news_index(
            html,
            &agency,
            &page,
            parse_date("2026-09-20").unwrap(),
            parse_date("2026-09-30").unwrap(),
        );
        assert_eq!(items.len(), 1);
        assert!(items[0].link.ends_with(expected));
        let unrelated = parse_catalog_news_index(
            html,
            &agency,
            &format!("https://{host}/news/"),
            parse_date("2026-09-20").unwrap(),
            parse_date("2026-09-30").unwrap(),
        );
        assert!(unrelated.is_empty());
    }
}

#[test]
fn ni_indexes_require_explicit_year_and_exclude_detail_related_cards() {
    let html = include_str!("../../../../tests/fixtures/catalog_ni_indexes.html");
    for (host, path, expected, day) in [
        ("www.cvsni.org", "/news/", "victims", "18"),
        ("www.publichealth.hscni.net", "/news", "health", "25"),
        (
            "www.stmarys-belfast.ac.uk",
            "/about-us/news/",
            "university",
            "29",
        ),
    ] {
        let page = format!("https://{host}{path}");
        let agency = Agency {
            name_zh: "Official".into(),
            name_en: "Official".into(),
            short_name: "catalog:test".into(),
            homepage: page.clone(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let items = parse_catalog_news_index(
            html,
            &agency,
            &page,
            parse_date("2026-09-01").unwrap(),
            parse_date("2026-09-30").unwrap(),
        );
        assert_eq!(items.len(), 1, "{host}");
        assert!(items[0].link.ends_with(expected));
        assert_eq!(items[0].published_at.format("%d").to_string(), day);
        assert!(parse_catalog_news_index(
            html,
            &agency,
            &format!("https://{host}/news/detail"),
            parse_date("2026-09-01").unwrap(),
            parse_date("2026-09-30").unwrap()
        )
        .is_empty());
    }
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
    let has_json_ld = doc
        .select(&Selector::parse("script[type='application/ld+json']").unwrap())
        .next()
        .is_some();
    if !is_agency_homepage(page_url, &agency.homepage)
        && (content_page || explicit_article_date.is_some() || has_json_ld)
    {
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
                        &doc.root_element().text().collect::<Vec<_>>().join(" "),
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
        if is_agency_homepage(&link, &agency.homepage) {
            continue;
        }
        if link
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
            &c.text().collect::<Vec<_>>().join(" "),
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
    context: &str,
) -> NewsItem {
    NewsItem {
        agency: a.display_name(),
        agency_en: a.name_en.clone(),
        unit_category: Some(a.short_name.clone()),
        content_type: content_type_for_link(&link, &title, context),
        title: clean_text(&title),
        link,
        published_at,
        summary: clean_text(&summary),
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

pub fn parse_catalog_news_index(
    html: &str,
    agency: &Agency,
    page_url: &str,
    since: DateTime<Utc>,
    until: DateTime<Utc>,
) -> Vec<NewsItem> {
    // Catalog HTML sources are indexes: only explicitly dated linked cards belong here.
    let mut seen = std::collections::HashSet::new();
    let document = Html::parse_document(html);
    let base = Url::parse(page_url).ok();
    let cards = Selector::parse("article, li, .search-result, .card, .views-row, .news-listing, .newsResult__item, .news-list__item, a.list__item, a.homepage-panel-link, .news-result, .card-body, .featuredItemContent, .contentContainer").unwrap();
    let anchors = [
        "h2 a[href]",
        "h3 a[href]",
        "h4 a[href]",
        ".views-field-title a[href]",
        "a[href]",
    ]
    .map(|value| Selector::parse(value).unwrap());
    let time_selector = Selector::parse("time").unwrap();
    let metadata = Selector::parse("dl.ds_metadata dt").unwrap();
    let date_values = Selector::parse(".ds_news-item__meta p, .PubDate p, .card-text small, .newsResult__date, .post-meta .published, .news-list__date, .listing-item p, .updated, .homepage-panel-footer small, .news-result p.date, .card-body p.article-date, .featuredItemContent span.date, .card-meta p.date, .contentContainer p.date, p.pub-date").unwrap();
    let structured_anchors = Selector::parse(
        "a.stretched-link[href], a.card-link[href], a.newsResult__cta[href], a.link--cover[href], a.cover[href]",
    )
    .unwrap();
    let structured_titles = Selector::parse(
        ".card-title, .newsResult__itemTitle, .news-list__title, .card-main h3.title",
    )
    .unwrap();
    let headings = Selector::parse("h2, h3").unwrap();
    let semantic_date = Selector::parse("span[property='dc:date'][content]").unwrap();
    let host = base
        .as_ref()
        .and_then(|value| value.host_str())
        .map(normalize_host)
        .unwrap_or_default();
    let index_rule = match host.as_str() {
        "cvsni.org" => Some(("article", "a.no-underline[href]", "h2", "p.italic")),
        "publichealth.hscni.net" => Some((
            ".node--type-news",
            "h3 a[href]",
            "h3 a[href]",
            ".node--type-news > p strong",
        )),
        "stmarys-belfast.ac.uk" => Some(("a.news-item", ":self", "h4", ".text-pale-sky")),
        "ukri.org"
            if base.as_ref().is_some_and(|base| {
                base.path().trim_end_matches('/') == "/councils/research-england/news"
            }) =>
        {
            Some((
                ".category-research-england",
                "a[href]",
                ".entry-title",
                ".post-summary__date",
            ))
        }
        "audit.scot"
            if base.as_ref().is_some_and(|base| {
                base.path().trim_end_matches('/') == "/accounts-commission"
            }) =>
        {
            Some((".ac-latest-news > div", "h3 a[href]", "h3 a[href]", "time"))
        }
        "portonbiopharma.com" => Some(("a.post-item-inner", ":self", "h3", ".post-date")),
        "prosecutioninspectorate.scot" => {
            Some((".news-landing", "h2 a[href]", "h2 a[href]", ".article-date"))
        }
        "hmfsi.scot" => Some((
            ".publication-list-item",
            "h2 a[href]",
            "h2 a[href]",
            ".meta-date",
        )),
        "hmics.scot" => Some((
            ".article-landing-list-item",
            "h2 a[href]",
            "h2 a[href]",
            ".meta-date",
        )),
        "oscr.org.uk" => Some((".news-item", "a[href]", "h3", ".date")),
        "fuelpovertypanel.scot" => Some((
            "li.ds_category-item",
            "h3 a[href]",
            "h3 a[href]",
            ".publishedDate",
        )),
        "qmscotland.co.uk" => Some((".featured-article", "a[href]", "h2", ".date")),
        "ombudsman.wales" => Some((
            ".newslist-item",
            "a.newslist-item-link",
            "a.newslist-item-link",
            ".newslist-item-date",
        )),
        "uksbs.co.uk" => Some((".card", ".content a[href]", ".content h3", "p.article-date")),
        "consumer.scot" => Some((
            "article",
            "a.news-item__link",
            ".news-item__title",
            ".news-item__link-date",
        )),
        "crownestatescotland.com" => Some((
            ".views-view-responsive-grid__item",
            "a[href]",
            "a[href]",
            ".views-field-localgov-news-date",
        )),
        "nhshighland.scot.nhs.uk" => Some((
            ".featured-article, .article",
            "a[href]",
            ".article__title",
            ".article__detail",
        )),
        "pirc.scot" => Some((
            ".publication-item",
            "a.publication-item--heading",
            "h3",
            ".publication-item--date",
        )),
        "scottishcanals.co.uk" => Some((
            ".entry-card",
            "h2 a[href]",
            "h2 a[href]",
            "dd.entry-card-meta-value",
        )),
        "housingregulator.gov.scot" => Some(("a.signpost--news", ":self", "h2", ".signpost__date")),
        "southofscotlandenterprise.com" => Some((".items .item", "a[href]", "h3", "a > p")),
        "foi.scot" => Some((".intro_desc > p", "a[href]", "a[href]", ":prefix")),
        _ => None,
    };
    let restricted_index = match host.as_str() {
        "cvsni.org" | "publichealth.hscni.net" => Some("/news"),
        "stmarys-belfast.ac.uk" => Some("/about-us/news"),
        _ => None,
    };
    if restricted_index.is_some_and(|expected| {
        base.as_ref()
            .is_none_or(|base| base.path().trim_end_matches('/') != expected)
    }) {
        return Vec::new();
    }
    let rule_cards = index_rule.map(|rule| Selector::parse(rule.0).unwrap());
    if host == "ukri.org" && index_rule.is_none() {
        return Vec::new();
    }
    let slab_links = Selector::parse("a.page-listing-link[href]").unwrap();
    let mwc_cards = Selector::parse(".sp-content").unwrap();
    let fss_cards = Selector::parse("a.grid-card[href]").unwrap();
    let mwc_links = Selector::parse("a.slink[href]").unwrap();
    let specific_dates = Selector::parse(if host == "slab.org.uk" {
        "p.date-display"
    } else if host == "mwcscot.org.uk" {
        "p.meek"
    } else if host == "foodstandards.gov.scot" {
        ".grid-card-info date"
    } else {
        ":not(*)"
    })
    .unwrap();
    let mut card_nodes = document.select(&cards).collect::<Vec<_>>();
    if let Some(selector) = &rule_cards {
        if host == "ukri.org" {
            card_nodes = document.select(selector).collect();
        } else {
            card_nodes.extend(document.select(selector));
        }
    }
    if host == "slab.org.uk" {
        card_nodes.extend(
            document
                .select(&slab_links)
                .filter_map(|anchor| anchor.parent().and_then(scraper::ElementRef::wrap)),
        );
    } else if host == "mwcscot.org.uk" {
        card_nodes.extend(document.select(&mwc_cards));
    } else if host == "foodstandards.gov.scot" {
        card_nodes.extend(document.select(&fss_cards));
    }
    let mut items = Vec::new();
    for card in card_nodes {
        let matched_rule = rule_cards
            .as_ref()
            .is_some_and(|selector| selector.matches(&card));
        let pair = if matched_rule {
            let rule = index_rule.unwrap();
            let anchor = if rule.1 == ":self" {
                Some(card)
            } else {
                card.select(&Selector::parse(rule.1).unwrap()).next()
            };
            anchor.zip(card.select(&Selector::parse(rule.2).unwrap()).next())
        } else if card.value().name() == "a" {
            card.select(&headings).next().map(|title| (card, title))
        } else if let (Some(anchor), Some(title)) = (
            card.select(&structured_anchors).next(),
            card.select(&structured_titles).next(),
        ) {
            Some((anchor, title))
        } else if card
            .value()
            .classes()
            .any(|class| class == "contentContainer")
        {
            anchors
                .iter()
                .find_map(|selector| card.select(selector).next())
                .zip(card.select(&headings).next())
        } else if host == "slab.org.uk" && card.select(&slab_links).next().is_some() {
            card.select(&slab_links)
                .next()
                .zip(card.select(&headings).next())
        } else if host == "mwcscot.org.uk"
            && card.value().classes().any(|value| value == "sp-content")
        {
            card.select(&mwc_links)
                .next()
                .zip(card.select(&headings).next())
        } else {
            anchors
                .iter()
                .find_map(|selector| card.select(selector).next())
                .map(|anchor| (anchor, anchor))
        };
        let Some((anchor, title_node)) = pair else {
            continue;
        };
        let raw_date = if matched_rule {
            let rule = index_rule.unwrap();
            if rule.3 == ":prefix" {
                card.text()
                    .collect::<Vec<_>>()
                    .join(" ")
                    .split(" - ")
                    .next()
                    .unwrap_or_default()
                    .to_owned()
            } else {
                card.select(&Selector::parse(rule.3).unwrap())
                    .find_map(|node| {
                        let raw = node.text().collect::<Vec<_>>().join(" ");
                        let raw = raw.split_whitespace().collect::<Vec<_>>().join(" ");
                        let raw = if host == "ukri.org" {
                            raw.strip_prefix("Pinned article from ")
                                .unwrap_or(&raw)
                                .to_owned()
                        } else {
                            raw
                        };
                        parse_date(&raw).map(|_| raw)
                    })
                    .unwrap_or_default()
            }
        } else if let Some(time) = card.select(&time_selector).next() {
            time.value()
                .attr("datetime")
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
                .unwrap_or_else(|| time.text().collect::<Vec<_>>().join(" "))
        } else {
            card.select(&semantic_date)
                .next()
                .and_then(|value| value.value().attr("content").map(str::to_owned))
                .or_else(|| {
                    card.select(&metadata).find_map(|label| {
                        if label
                            .text()
                            .collect::<Vec<_>>()
                            .join(" ")
                            .trim()
                            .to_lowercase()
                            != "date"
                        {
                            return None;
                        }
                        label
                            .next_siblings()
                            .filter_map(scraper::ElementRef::wrap)
                            .find(|value| value.value().name() == "dd")
                            .map(|value| value.text().collect::<Vec<_>>().join(" "))
                    })
                })
                .or_else(|| {
                    card.select(&date_values)
                        .chain(card.select(&specific_dates))
                        .collect::<Vec<_>>()
                        .into_iter()
                        .rev()
                        .find_map(|value| {
                            let raw = value.text().collect::<Vec<_>>().join(" ");
                            if value.value().classes().any(|class| class == "updated")
                                && !raw.trim().starts_with("Published:")
                            {
                                return None;
                            }
                            let candidate = raw
                                .trim()
                                .strip_prefix("Published:")
                                .unwrap_or(raw.trim())
                                .trim();
                            parse_date(candidate).map(|_| candidate.to_owned())
                        })
                })
                .unwrap_or_default()
        };
        let Some(published) = parse_date(&raw_date) else {
            continue;
        };
        let title = clean_text(&title_node.text().collect::<Vec<_>>().join(" "));
        let Some(link) = base.as_ref().and_then(|base| {
            anchor
                .value()
                .attr("href")
                .and_then(|href| base.join(href).ok())
        }) else {
            continue;
        };
        if title.chars().count() < 12
            || published < since
            || published >= until
            || link.host_str() != base.as_ref().and_then(|base| base.host_str())
            || link.path().to_lowercase().ends_with(".pdf")
            || link.as_str() == page_url
            || !seen.insert(link.to_string())
        {
            continue;
        }
        items.push(news(
            agency,
            title,
            link.to_string(),
            published,
            page_url.into(),
            String::new(),
            &card.text().collect::<Vec<_>>().join(" "),
        ));
    }
    if host == "nhstayside.scot.nhs.uk" {
        let intro_selector =
            Selector::parse(".news-short-article > .news-short-article-intro").unwrap();
        let anchor_selector = Selector::parse("a[href]").unwrap();
        for intro in document.select(&intro_selector) {
            let Some(date_node) = intro
                .prev_siblings()
                .filter_map(scraper::ElementRef::wrap)
                .next()
            else {
                continue;
            };
            if !date_node
                .value()
                .classes()
                .any(|value| value == "news-short-article-date")
            {
                continue;
            }
            let Some(published) = parse_date(&date_node.text().collect::<Vec<_>>().join(" "))
            else {
                continue;
            };
            let Some(anchor) = intro.select(&anchor_selector).next() else {
                continue;
            };
            let title = clean_text(&anchor.text().collect::<Vec<_>>().join(" "));
            let Some(link) = base.as_ref().and_then(|base| {
                anchor
                    .value()
                    .attr("href")
                    .and_then(|href| base.join(href).ok())
            }) else {
                continue;
            };
            if title.chars().count() < 12
                || published < since
                || published >= until
                || link.host_str() != base.as_ref().and_then(|base| base.host_str())
                || link.path().to_lowercase().ends_with(".pdf")
                || !seen.insert(link.to_string())
            {
                continue;
            }
            let summary = intro
                .next_siblings()
                .filter_map(scraper::ElementRef::wrap)
                .next()
                .filter(|node| {
                    node.value()
                        .classes()
                        .any(|value| value == "news-short-article-text")
                })
                .map(|node| clean_text(&node.text().collect::<Vec<_>>().join(" ")))
                .unwrap_or_default();
            items.push(news(
                agency,
                title,
                link.to_string(),
                published,
                page_url.into(),
                summary.clone(),
                &summary,
            ));
        }
    }
    if Url::parse(page_url)
        .ok()
        .and_then(|url| url.host_str().map(str::to_owned))
        .is_some_and(|host| host == "www.supremecourt.uk" || host == "supremecourt.uk")
    {
        let document = Html::parse_document(html);
        let anchor_selector = Selector::parse("a[href^='/news/']").unwrap();
        let heading_selector = Selector::parse("[class*='line-clamp-2']").unwrap();
        let date_regex = regex::Regex::new(r"\b\d{1,2} [A-Za-z]+ \d{4}\b").unwrap();
        let base = Url::parse(page_url).unwrap();
        for anchor in document.select(&anchor_selector) {
            let Some(heading) = anchor.select(&heading_selector).next() else {
                continue;
            };
            let Some(link) = anchor
                .value()
                .attr("href")
                .and_then(|href| base.join(href).ok())
            else {
                continue;
            };
            if link.path() == "/news/latest-judgments" {
                continue;
            }
            let context = anchor.text().collect::<Vec<_>>().join(" ");
            let Some(date_match) = date_regex.find(&context) else {
                continue;
            };
            let Some(published) = parse_date(date_match.as_str()) else {
                continue;
            };
            let title = clean_text(&heading.text().collect::<Vec<_>>().join(" "));
            if title.chars().count() < 12
                || published < since
                || published >= until
                || !seen.insert(link.to_string())
            {
                continue;
            }
            items.push(news(
                agency,
                title,
                link.to_string(),
                published,
                page_url.into(),
                String::new(),
                &context,
            ));
        }
    }
    items
}
pub fn dedupe(items: Vec<NewsItem>) -> Vec<NewsItem> {
    let _timer = crate::performance::Timer::new("dedupe_work_seconds");
    let mut seen = std::collections::HashSet::new();
    let mut items = items;
    items.sort_by(|a, b| {
        b.published_at
            .cmp(&a.published_at)
            .then_with(|| {
                a.unit_category
                    .as_deref()
                    .unwrap_or(&a.agency)
                    .cmp(b.unit_category.as_deref().unwrap_or(&b.agency))
            })
            .then_with(|| a.link.cmp(&b.link))
            .then_with(|| a.title.cmp(&b.title))
    });
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
    fn shared_homepage_fixture_keeps_only_dated_articles() {
        let agency = crate::agencies()
            .into_iter()
            .find(|agency| agency.short_name == "BIST")
            .unwrap();
        let items = parse_feed_document(
            include_bytes!("../../../../tests/fixtures/agency_homepage_guard.xml"),
            &agency,
            "fixture",
            Utc.with_ymd_and_hms(2026, 9, 23, 0, 0, 0).unwrap(),
            Utc.with_ymd_and_hms(2026, 10, 8, 0, 0, 0).unwrap(),
        )
        .unwrap();
        assert_eq!(items.len(), 2);
        assert!(items
            .iter()
            .all(|item| !is_agency_homepage(&item.link, &agency.homepage)));
        assert!(items
            .iter()
            .any(|item| item.content_type == ContentType::Guidance));
        let html = r#"<h1>Department homepage</h1><meta property="article:published_time" content="2026-10-01T00:00:00Z">"#;
        assert!(parse_official_html(
            html,
            &agency,
            &agency.homepage,
            Utc.with_ymd_and_hms(2026, 9, 23, 0, 0, 0).unwrap(),
            Utc.with_ymd_and_hms(2026, 10, 8, 0, 0, 0).unwrap()
        )
        .is_empty());
    }

    #[test]
    fn shared_feed_fixture_preserves_valid_item() {
        let agency = Agency {
            name_zh: "官方機關".into(),
            name_en: "Official".into(),
            short_name: "court-test:judgments".into(),
            homepage: "https://official.example".into(),
            feeds: vec!["https://official.example/feed".into()],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let items = parse_feed_document(
            include_bytes!("../../../../tests/fixtures/source_parser_v1.xml"),
            &agency,
            "https://official.example/feed",
            Utc.with_ymd_and_hms(2026, 9, 23, 0, 0, 0).unwrap(),
            Utc.with_ymd_and_hms(2026, 9, 24, 0, 0, 0).unwrap(),
        )
        .unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].content_type, ContentType::Judgment);
    }
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

    #[test]
    fn shared_link_uses_stable_source_order() {
        let agency = Agency {
            name_zh: "Alpha".into(),
            name_en: "Alpha".into(),
            short_name: "govuk:alpha".into(),
            homepage: "https://www.gov.uk/".into(),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let xml = r#"<feed xmlns="http://www.w3.org/2005/Atom"><title>Test</title><id>test</id><updated>2026-07-28T00:00:00Z</updated><entry><title>Shared</title><id>one</id><updated>2026-07-28T00:00:00Z</updated><link href="https://www.gov.uk/government/news/shared"/></entry></feed>"#;
        let since = Utc.with_ymd_and_hms(2026, 7, 28, 0, 0, 0).unwrap();
        let until = Utc.with_ymd_and_hms(2026, 7, 29, 0, 0, 0).unwrap();
        let alpha = parse_feed_document(xml.as_bytes(), &agency, "test", since, until)
            .unwrap()
            .remove(0);
        let mut beta = alpha.clone();
        beta.agency = "Beta".into();
        beta.unit_category = Some("govuk:beta".into());
        assert_eq!(
            dedupe(vec![beta.clone(), alpha.clone()])[0].agency,
            agency.display_name()
        );
        assert_eq!(dedupe(vec![alpha, beta])[0].agency, agency.display_name());
    }
}
#[test]
fn catalog_html_filters_foreign_future_undated_and_index_records() {
    let agency = Agency {
        name_zh: "官方機關".into(),
        name_en: "Official Agency".into(),
        short_name: "test".into(),
        homepage: "https://official.example/".into(),
        feeds: vec![],
        news_pages: vec![],
        topics: vec![],
        link_include_patterns: vec![],
        official_pages: vec![],
    };
    let html = include_str!("../../../../tests/fixtures/catalog_news_index.html");
    let since = DateTime::parse_from_rfc3339("2026-09-24T00:00:00Z")
        .unwrap()
        .with_timezone(&Utc);
    let until = DateTime::parse_from_rfc3339("2026-09-26T00:00:00Z")
        .unwrap()
        .with_timezone(&Utc);
    let items =
        parse_catalog_news_index(html, &agency, "https://official.example/news", since, until);
    assert_eq!(items.len(), 2);
    assert!(items.iter().any(
        |item| item.link == "https://official.example/news/digital-policy"
            && item.content_type == ContentType::Publication
    ));
    assert!(items
        .iter()
        .any(|item| item.link == "https://official.example/reports/ai"
            && item.content_type == ContentType::Report));
}

#[test]
fn textual_feed_dates_and_minute_precision_index_dates_are_preserved() {
    let xml = br#"<rss version="2.0"><channel><title>Official</title><link>https://official.example/</link><description>News</description><item><title>Health in D&#038;G</title><link>https://official.example/news/health</link><pubDate>25 September 2026</pubDate></item></channel></rss>"#;
    let feed = parse_feed_with_dates(xml).unwrap();
    assert_eq!(
        feed.entries[0].published.unwrap().to_rfc3339(),
        "2026-09-25T00:00:00+00:00"
    );
    assert_eq!(
        clean_text(&feed.entries[0].title.as_ref().unwrap().content),
        "Health in D&G"
    );
    assert_eq!(
        parse_date("2025-12-4T10:36Z").unwrap().to_rfc3339(),
        "2025-12-04T10:36:00+00:00"
    );
    assert_eq!(
        parse_date("2025-11-21T14:00Z").unwrap().to_rfc3339(),
        "2025-11-21T14:00:00+00:00"
    );
}

#[test]
fn official_search_text_normalizes_whitespace_and_apostrophes() {
    assert_eq!(
        clean_text("Monthly  estimates\r\nHMRC’s data "),
        "Monthly estimates HMRC's data"
    );
}

#[test]
fn catalog_cards_use_explicit_metadata_dates_and_article_links() {
    let agency = Agency {
        name_zh: "Official".into(),
        name_en: "Official".into(),
        short_name: "catalog:test".into(),
        homepage: "https://official.example/".into(),
        feeds: vec![],
        news_pages: vec![],
        topics: vec![],
        link_include_patterns: vec![],
        official_pages: vec![],
    };
    let since = parse_date("2026-09-20").unwrap();
    let until = parse_date("2026-09-30").unwrap();
    let items = parse_catalog_news_index(
        include_str!("../../../../tests/fixtures/catalog_explicit_dates.html"),
        &agency,
        "https://official.example/news",
        since,
        until,
    );
    assert_eq!(items.len(), 16);
    assert!(items.iter().any(|item| item.link.ends_with("/semantic")
        && item.published_at.to_rfc3339() == "2026-09-29T11:00:00+00:00"));
    assert!(items.iter().any(|item| item.link.ends_with("/views")));
    assert!(!items.iter().any(|item| item.link.ends_with("/category")));
    assert!(!items.iter().any(|item| item.link.ends_with("/updated")
        || item.link.ends_with("/unlabelled-update")
        || item.link.ends_with("/generic-date")));
}

#[test]
fn atom_plain_text_titles_preserve_literal_angle_brackets() {
    let agency = Agency {
        name_zh: "Official".into(),
        name_en: "Official".into(),
        short_name: "catalog:test".into(),
        homepage: "https://official.example/".into(),
        feeds: vec![],
        news_pages: vec![],
        topics: vec![],
        link_include_patterns: vec![],
        official_pages: vec![],
    };
    for (kind, expected) in [
        ("text", "Official <news> announcement & guidance"),
        ("html", "Official announcement & guidance"),
    ] {
        let xml = format!(
            r#"<feed xmlns="http://www.w3.org/2005/Atom"><id>f</id><title>Official</title>
          <updated>2026-09-25T00:00:00Z</updated><entry><id>one</id>
          <title type="{kind}">Official &lt;news&gt; announcement &amp; guidance</title>
          <link href="https://official.example/news/one"/><updated>2026-09-25T00:00:00Z</updated>
          </entry></feed>"#
        );
        let items = parse_feed_document(
            xml.as_bytes(),
            &agency,
            "feed",
            parse_date("2026-09-20").unwrap(),
            parse_date("2026-09-30").unwrap(),
        )
        .unwrap();
        assert_eq!(items[0].title, expected);
    }
}

#[test]
fn host_specific_publication_fields_do_not_apply_to_unrelated_sites() {
    let html = include_str!("../../../../tests/fixtures/catalog_host_dates.html");
    for (host, expected) in [
        ("www.slab.org.uk", "legal-aid"),
        ("www.mwcscot.org.uk", "mental-health"),
        ("www.foodstandards.gov.scot", "food-safety"),
        ("official.example", ""),
    ] {
        let agency = Agency {
            name_zh: "Official".into(),
            name_en: "Official".into(),
            short_name: "catalog:test".into(),
            homepage: format!("https://{host}/"),
            feeds: vec![],
            news_pages: vec![],
            topics: vec![],
            link_include_patterns: vec![],
            official_pages: vec![],
        };
        let items = parse_catalog_news_index(
            html,
            &agency,
            &format!("https://{host}/news"),
            parse_date("2026-09-01").unwrap(),
            parse_date("2026-09-30").unwrap(),
        );
        if expected.is_empty() {
            assert!(items.is_empty());
        } else {
            assert_eq!(items.len(), 1);
            assert!(items[0].link.ends_with(expected));
        }
    }
}

#[test]
fn feed_content_supplies_missing_summary_but_preserves_explicit_summary() {
    let agency = Agency {
        name_zh: "Official".into(),
        name_en: "Official".into(),
        short_name: "catalog:test".into(),
        homepage: "https://official.example/".into(),
        feeds: vec![],
        news_pages: vec![],
        topics: vec![],
        link_include_patterns: vec![],
        official_pages: vec![],
    };
    let items = parse_feed_document(
        include_bytes!("../../../../tests/fixtures/catalog_content_feed.xml"),
        &agency,
        "feed",
        parse_date("2026-09-20").unwrap(),
        parse_date("2026-09-30").unwrap(),
    )
    .unwrap();
    assert_eq!(
        items
            .iter()
            .map(|item| item.summary.as_str())
            .collect::<Vec<_>>(),
        [
            "The Board's official update is published.",
            "Short official summary"
        ]
    );
}

#[test]
fn tayside_sibling_dates_and_summaries_are_bound_to_each_headline() {
    let html = include_str!("../../../../tests/fixtures/catalog_tayside.html");
    let page = "https://www.nhstayside.scot.nhs.uk/News/index.htm";
    let agency = Agency {
        name_zh: "Official".into(),
        name_en: "Official".into(),
        short_name: "catalog:test".into(),
        homepage: page.into(),
        feeds: vec![],
        news_pages: vec![],
        topics: vec![],
        link_include_patterns: vec![],
        official_pages: vec![],
    };
    let items = parse_catalog_news_index(
        html,
        &agency,
        page,
        parse_date("2026-09-20").unwrap(),
        parse_date("2026-09-30").unwrap(),
    );
    assert_eq!(items.len(), 2);
    assert_eq!(
        items[0].published_at.to_rfc3339(),
        "2026-09-25T00:00:00+00:00"
    );
    assert_eq!(items[0].summary, "First summary");
    assert_eq!(
        items[1].published_at.to_rfc3339(),
        "2026-09-24T00:00:00+00:00"
    );
    assert_eq!(
        items[1].summary,
        "Second summary with reference to 11 September 2026"
    );
    assert!(parse_catalog_news_index(
        html,
        &agency,
        "https://official.example/news",
        parse_date("2026-09-20").unwrap(),
        parse_date("2026-09-30").unwrap()
    )
    .is_empty());
}
