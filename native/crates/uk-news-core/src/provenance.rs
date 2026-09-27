use crate::{NewsItem, ParliamentBriefing, RecordProvenance, SourceHealth};

pub const PARSER_VERSION: &str = "v1";

pub fn canonical_url(value: &str) -> String {
    let Ok(mut parsed) = url::Url::parse(value.trim()) else {
        return value.trim().into();
    };
    parsed.set_query(None);
    parsed.set_fragment(None);
    let path = parsed.path().trim_end_matches('/').to_string();
    parsed.set_path(if path.is_empty() { "/" } else { &path });
    parsed.to_string()
}

pub fn record_provenance(
    news: &[NewsItem],
    parliament: &[ParliamentBriefing],
    fetched_at: &str,
    source_health: &[SourceHealth],
) -> Vec<RecordProvenance> {
    let observed_at = |source: &str| {
        source_health
            .iter()
            .find(|health| health.source == source && !health.fetched_at.is_empty())
            .map(|health| health.fetched_at.as_str())
            .unwrap_or(fetched_at)
            .to_string()
    };
    let mut records = news
        .iter()
        .map(|item| RecordProvenance {
            record_type: "news".into(),
            source_id: item
                .unit_category
                .clone()
                .unwrap_or_else(|| item.agency.clone()),
            url: item.link.clone(),
            canonical_url: canonical_url(&item.link),
            source_feed: item.source_feed.clone(),
            fetched_at: observed_at(item.unit_category.as_deref().unwrap_or(&item.agency)),
            parser_version: PARSER_VERSION.into(),
        })
        .collect::<Vec<_>>();
    records.extend(parliament.iter().map(|item| RecordProvenance {
        record_type: "parliament".into(),
        source_id: item.publisher.clone(),
        url: item.webpage_url.clone(),
        canonical_url: canonical_url(&item.webpage_url),
        source_feed: item.fetched_from.clone(),
        fetched_at: observed_at(&format!("{} RSS", item.publisher)),
        parser_version: PARSER_VERSION.into(),
    }));
    records.sort_by(|a, b| {
        (&a.record_type, &a.source_id, &a.canonical_url).cmp(&(
            &b.record_type,
            &b.source_id,
            &b.canonical_url,
        ))
    });
    records
}
