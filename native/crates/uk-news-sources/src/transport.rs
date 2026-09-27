use chrono::{DateTime, Utc};
use reqwest::{header::RETRY_AFTER, RequestBuilder, StatusCode};
use sha2::{Digest, Sha256};
use std::{collections::HashMap, sync::Arc, time::Duration};
use tokio::{
    sync::{Mutex, Semaphore},
    time::{timeout_at, Instant},
};
use uk_news_core::EndpointObservation;

#[derive(Clone)]
pub struct Transport {
    client: reqwest::Client,
    slots: Arc<Mutex<HashMap<String, Arc<Semaphore>>>>,
    deadline: Instant,
}

impl Transport {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::builder()
                .user_agent("UK-news-observation-scraper/2.0")
                .timeout(Duration::from_secs(8))
                .build()
                .expect("valid HTTP client"),
            slots: Arc::new(Mutex::new(HashMap::new())),
            deadline: Instant::now() + Duration::from_secs(50),
        }
    }

    pub fn get(&self, url: &str) -> RequestBuilder {
        self.client.get(url)
    }

    pub async fn bytes(
        &self,
        builder: RequestBuilder,
        observations: &mut Vec<EndpointObservation>,
    ) -> Result<Vec<u8>, String> {
        let request = builder.build().map_err(|error| error.to_string())?;
        let mut endpoint_url = request.url().clone();
        endpoint_url.set_query(None);
        endpoint_url.set_fragment(None);
        let host = endpoint_url.host_str().unwrap_or("").to_lowercase();
        let slot = {
            let mut slots = self.slots.lock().await;
            slots
                .entry(host)
                .or_insert_with(|| Arc::new(Semaphore::new(2)))
                .clone()
        };
        for attempt in 0..2 {
            let _permit = timeout_at(self.deadline, slot.clone().acquire_owned())
                .await
                .map_err(|_| "本次抓取已達整體等待上限".to_string())?
                .map_err(|error| error.to_string())?;
            let repeat = request.try_clone().ok_or("GET request cannot be retried")?;
            let response = match timeout_at(self.deadline, self.client.execute(repeat)).await {
                Ok(Ok(response)) => response,
                Ok(Err(error)) => {
                    observations.push(empty_observation(endpoint_url.as_str()));
                    return Err(error.to_string());
                }
                Err(_) => {
                    observations.push(empty_observation(endpoint_url.as_str()));
                    return Err("本次抓取已達整體等待上限".into());
                }
            };
            let status = response.status();
            let delay = retry_after(
                response
                    .headers()
                    .get(RETRY_AFTER)
                    .and_then(|v| v.to_str().ok()),
            );
            let etag = response
                .headers()
                .get("etag")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_string();
            let last_modified = response
                .headers()
                .get("last-modified")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("")
                .to_string();
            let body = match timeout_at(self.deadline, response.bytes()).await {
                Ok(Ok(body)) => body,
                outcome => {
                    observations.push(EndpointObservation {
                        url: endpoint_url.to_string(),
                        status_code: status.as_u16(),
                        fetched_at: Utc::now().to_rfc3339(),
                        response_sha256: String::new(),
                        etag,
                        last_modified,
                        bytes_count: 0,
                    });
                    return Err(match outcome {
                        Ok(Err(error)) => error.to_string(),
                        Err(_) => "本次抓取已達整體等待上限".into(),
                        Ok(Ok(_)) => unreachable!(),
                    });
                }
            };
            observations.push(EndpointObservation {
                url: endpoint_url.to_string(),
                status_code: status.as_u16(),
                fetched_at: Utc::now().to_rfc3339(),
                response_sha256: format!("{:x}", Sha256::digest(&body)),
                etag,
                last_modified,
                bytes_count: body.len(),
            });
            if attempt == 0
                && matches!(
                    status,
                    StatusCode::TOO_MANY_REQUESTS | StatusCode::SERVICE_UNAVAILABLE
                )
            {
                if Instant::now() + delay >= self.deadline {
                    return Err(format!("HTTP {status}；伺服器要求延後重試"));
                }
                tokio::time::sleep(delay).await;
                continue;
            }
            if !status.is_success() {
                return Err(format!("HTTP {status}"));
            }
            return Ok(body.to_vec());
        }
        Err("bounded request loop exhausted".into())
    }
}

fn retry_after(value: Option<&str>) -> Duration {
    let Some(value) = value else {
        return Duration::from_secs(1);
    };
    if let Ok(seconds) = value.parse::<u64>() {
        return Duration::from_secs(seconds);
    }
    DateTime::parse_from_rfc2822(value)
        .ok()
        .and_then(|date| (date.with_timezone(&Utc) - Utc::now()).to_std().ok())
        .unwrap_or(Duration::from_secs(1))
}

fn empty_observation(url: &str) -> EndpointObservation {
    EndpointObservation {
        url: url.into(),
        status_code: 0,
        fetched_at: Utc::now().to_rfc3339(),
        response_sha256: String::new(),
        etag: String::new(),
        last_modified: String::new(),
        bytes_count: 0,
    }
}
