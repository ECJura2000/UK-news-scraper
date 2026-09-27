use crate::{RunObservability, SourceHealth};

pub fn summarize_source_health(health: &[SourceHealth]) -> RunObservability {
    let sources = health
        .iter()
        .filter(|source| source.critical)
        .collect::<Vec<_>>();
    if sources.is_empty() {
        return RunObservability {
            source_success_rate: 1.0,
            ..Default::default()
        };
    }
    let count = sources.len();
    let success_rate = sources.iter().filter(|source| source.success).count() as f64 / count as f64;
    let zero_ratio = sources
        .iter()
        .filter(|source| source.item_count == 0)
        .count() as f64
        / count as f64;
    let mut durations = sources
        .iter()
        .map(|source| source.duration_seconds)
        .collect::<Vec<_>>();
    durations.sort_by(f64::total_cmp);
    let p95 = durations[(count * 95).div_ceil(100) - 1];
    let mut alerts = Vec::new();
    if success_rate < 0.90 {
        alerts.push("source_success_rate".into());
    }
    if p95 > 60.0 {
        alerts.push("source_p95_seconds".into());
    }
    if zero_ratio > 0.25 {
        alerts.push("zero_item_ratio".into());
    }
    RunObservability {
        source_count: count,
        source_success_rate: round_three(success_rate),
        source_p95_seconds: round_three(p95),
        zero_item_ratio: round_three(zero_ratio),
        alerts,
    }
}

fn round_three(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn shared_source_contract() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/source_contract_v1.json"
        ))
        .unwrap();
        let health: Vec<SourceHealth> = serde_json::from_value(fixture["health"].clone()).unwrap();
        let actual = serde_json::to_value(summarize_source_health(&health)).unwrap();
        assert_eq!(actual, fixture["expected_observability"]);
        for value in fixture["canonical_urls"].as_array().unwrap() {
            assert_eq!(
                crate::canonical_url(value["raw"].as_str().unwrap()),
                value["expected"].as_str().unwrap()
            );
        }
    }
}
