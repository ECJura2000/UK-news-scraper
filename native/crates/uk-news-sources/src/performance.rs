//! Task-scoped, shared diagnostics for a run and its concurrently polled futures.
use std::{
    sync::{Arc, Mutex},
    time::Instant,
};
use uk_news_core::RunPerformance;

pub type Recorder = Arc<Mutex<RunPerformance>>;
tokio::task_local! { pub static CURRENT: Recorder; }

pub fn record(update: impl FnOnce(&mut RunPerformance)) {
    let _ = CURRENT.try_with(|recorder| {
        if let Ok(mut data) = recorder.lock() {
            update(&mut data);
        }
    });
}

pub struct Timer {
    name: &'static str,
    started: Instant,
}
impl Timer {
    pub fn new(name: &'static str) -> Self {
        Self {
            name,
            started: Instant::now(),
        }
    }
}
impl Drop for Timer {
    fn drop(&mut self) {
        record(|data| {
            let duration = data.stages.entry(self.name.into()).or_default();
            *duration = Some(duration.unwrap_or(0.0) + self.started.elapsed().as_secs_f64());
        });
    }
}

pub fn route_category(url: &str) -> &'static str {
    if let Ok(url) = url::Url::parse(url) {
        if url.host_str() == Some("news.google.com") {
            return "fallback";
        }
        if url.path().ends_with("/api/search.json") || url.path().contains("researchbriefings.json")
        {
            return "search_api";
        }
    }
    "list"
}

pub fn http_attempt(category: &str, retry: bool) {
    record(|data| {
        let counts = data.http.entry(category.into()).or_default();
        counts.attempted_count += 1;
        counts.retry_count += usize::from(retry);
    });
}

pub fn http_status(category: &str, status: u16) {
    if status == 429 {
        record(|data| {
            data.http
                .entry(category.into())
                .or_default()
                .rate_limited_count += 1
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn concurrent_runs_do_not_share_metrics() {
        let first = Recorder::default();
        let second = Recorder::default();
        let job = || async {
            let _timer = Timer::new("dedupe_work_seconds");
            http_attempt("search_api", false);
            http_status("search_api", 429);
            tokio::task::yield_now().await;
            http_attempt("search_api", true);
        };
        tokio::join!(
            CURRENT.scope(first.clone(), job()),
            CURRENT.scope(second.clone(), job())
        );
        for recorder in [first, second] {
            let data = recorder.lock().unwrap();
            assert_eq!(data.http["search_api"].attempted_count, 2);
            assert_eq!(data.http["search_api"].retry_count, 1);
            assert_eq!(data.http["search_api"].rate_limited_count, 1);
            assert!(data.stages["dedupe_work_seconds"].unwrap() >= 0.0);
        }
        assert_eq!(
            route_category("https://news.google.com/rss/search"),
            "fallback"
        );
        assert_eq!(
            route_category("https://www.gov.uk/api/search.json"),
            "search_api"
        );
        assert_eq!(route_category("https://example.org/feed"), "list");
    }
}
