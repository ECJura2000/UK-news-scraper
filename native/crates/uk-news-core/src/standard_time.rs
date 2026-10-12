//! Bounded application SNTP clock. Never changes the operating-system clock.
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::net::{ToSocketAddrs, UdpSocket};
use std::sync::{mpsc, Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const SERVERS: [&str; 5] = [
    "tock.stdtime.gov.tw",
    "watch.stdtime.gov.tw",
    "time.stdtime.gov.tw",
    "clock.stdtime.gov.tw",
    "tick.stdtime.gov.tw",
];
const EPOCH: f64 = 2_208_988_800.0;
const ERA: f64 = 4_294_967_296.0;
const MAX_AGE: Duration = Duration::from_secs(1800);

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct TimeSync {
    pub source: String,
    pub server: String,
    pub checked_at: String,
    pub offset_seconds: Option<f64>,
    pub round_trip_seconds: Option<f64>,
    pub warning: String,
    pub attempts: Vec<Attempt>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Attempt {
    pub server: String,
    pub result: String,
}
impl Default for TimeSync {
    fn default() -> Self {
        Self {
            source: "system".into(),
            server: String::new(),
            checked_at: String::new(),
            offset_seconds: None,
            round_trip_seconds: None,
            warning: "尚未連接國家標準時間，使用本機時間".into(),
            attempts: vec![],
        }
    }
}
#[derive(Default)]
struct Clock {
    status: TimeSync,
    anchor: Option<(f64, Instant)>,
    last_attempt: Option<Instant>,
}
static CLOCK: OnceLock<Mutex<Clock>> = OnceLock::new();
fn clock() -> &'static Mutex<Clock> {
    CLOCK.get_or_init(|| Mutex::new(Clock::default()))
}
fn timestamp(raw: &[u8], reference: f64) -> f64 {
    let base = u32::from_be_bytes(raw[..4].try_into().unwrap()) as f64 - EPOCH
        + u32::from_be_bytes(raw[4..8].try_into().unwrap()) as f64 / ERA;
    base + ((reference - base) / ERA).round() * ERA
}
pub fn parse_reply(
    packet: &[u8],
    request: &[u8],
    sent: f64,
    received: f64,
) -> Result<(f64, f64), String> {
    if packet.len() < 48 || request.len() != 48 {
        return Err("NTP 封包長度錯誤".into());
    }
    if packet[0] >> 6 == 3 || ![3, 4].contains(&((packet[0] >> 3) & 7)) || packet[0] & 7 != 4 {
        return Err("NTP 伺服器未同步或回應模式錯誤".into());
    }
    if !(1..=15).contains(&packet[1]) {
        return Err("NTP 伺服器拒絕查詢或 stratum 無效".into());
    }
    if packet[24..32] != request[40..48] {
        return Err("NTP 回應不屬於本次查詢".into());
    }
    if packet[32..40].iter().all(|x| *x == 0) || packet[40..48].iter().all(|x| *x == 0) {
        return Err("NTP 回應缺少伺服器時間".into());
    }
    let (t2, t3) = (
        timestamp(&packet[32..40], received),
        timestamp(&packet[40..48], received),
    );
    let delay = (received - sent) - (t3 - t2);
    if t3 < t2 || !(-0.002..=2.0).contains(&delay) {
        return Err("NTP 網路延遲或伺服器時間無效".into());
    }
    Ok((((t2 - sent) + (t3 - received)) / 2.0, delay.max(0.0)))
}
fn encode(value: f64) -> [u8; 8] {
    let ntp = value + EPOCH;
    let mut raw = [0; 8];
    raw[..4].copy_from_slice(&((ntp.floor() as u64 % (1u64 << 32)) as u32).to_be_bytes());
    raw[4..].copy_from_slice(&((ntp.fract() * ERA) as u32).to_be_bytes());
    raw
}
struct Sample {
    utc: f64,
    anchor: Instant,
    offset: f64,
    delay: f64,
}
fn query(server: &str) -> Result<Sample, String> {
    let address = (server, 123)
        .to_socket_addrs()
        .map_err(|e| e.to_string())?
        .next()
        .ok_or("DNS 沒有回傳位址")?;
    let socket = UdpSocket::bind(if address.is_ipv4() {
        "0.0.0.0:0"
    } else {
        "[::]:0"
    })
    .map_err(|e| e.to_string())?;
    socket
        .set_read_timeout(Some(Duration::from_millis(800)))
        .map_err(|e| e.to_string())?;
    socket
        .set_write_timeout(Some(Duration::from_millis(800)))
        .map_err(|e| e.to_string())?;
    socket.connect(address).map_err(|e| e.to_string())?;
    let sent = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs_f64();
    let mut request = [0; 48];
    request[0] = 0x23;
    request[40..48].copy_from_slice(&encode(sent));
    let started = Instant::now();
    socket.send(&request).map_err(|e| e.to_string())?;
    let mut buffer = [0; 512];
    let count = socket.recv(&mut buffer).map_err(|e| e.to_string())?;
    let arrived = Instant::now();
    let received = sent + arrived.duration_since(started).as_secs_f64();
    let (offset, delay) = parse_reply(&buffer[..count], &request, sent, received)?;
    Ok(Sample {
        utc: received + offset,
        anchor: arrived,
        offset,
        delay,
    })
}
fn datetime(seconds: f64) -> DateTime<Utc> {
    DateTime::from_timestamp_micros((seconds * 1_000_000.0) as i64).unwrap_or_else(Utc::now)
}
pub fn synchronize(force: bool) -> TimeSync {
    let mut clock = clock().lock().unwrap();
    if !force
        && clock.last_attempt.is_some_and(|last| {
            last.elapsed()
                < if clock.anchor.is_some() {
                    MAX_AGE
                } else {
                    Duration::from_secs(60)
                }
        })
    {
        return clock.status.clone();
    }
    clock.last_attempt = Some(Instant::now());
    if std::env::var("UK_NEWS_TIME_SYNC")
        .unwrap_or_default()
        .eq_ignore_ascii_case("off")
    {
        clock.anchor = None;
        clock.status = TimeSync {
            checked_at: Utc::now().to_rfc3339(),
            warning: "NTP 校時已停用，使用本機時間".into(),
            ..Default::default()
        };
        return clock.status.clone();
    }
    let (tx, rx) = mpsc::channel();
    for server in SERVERS {
        let tx = tx.clone();
        std::thread::spawn(move || {
            let _ = tx.send((server, query(server)));
        });
    }
    drop(tx);
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut attempts = vec![];
    let mut best: Option<(&str, Sample)> = None;
    while let Ok((server, result)) =
        rx.recv_timeout(deadline.saturating_duration_since(Instant::now()))
    {
        match result {
            Ok(sample) => {
                attempts.push(Attempt {
                    server: server.into(),
                    result: "ok".into(),
                });
                if best
                    .as_ref()
                    .is_none_or(|(_, prior)| sample.delay < prior.delay)
                {
                    best = Some((server, sample));
                }
            }
            Err(error) => attempts.push(Attempt {
                server: server.into(),
                result: error,
            }),
        }
        if attempts.len() == SERVERS.len() {
            break;
        }
    }
    for server in SERVERS {
        if !attempts.iter().any(|a| a.server == server) {
            attempts.push(Attempt {
                server: server.into(),
                result: "查詢期限內未收到有效回應".into(),
            });
        }
    }
    if let Some((server, sample)) = best {
        clock.anchor = Some((sample.utc, sample.anchor));
        clock.status = TimeSync {
            source: "ntp".into(),
            server: server.into(),
            checked_at: datetime(sample.utc).to_rfc3339(),
            offset_seconds: Some(sample.offset),
            round_trip_seconds: Some(sample.delay),
            warning: String::new(),
            attempts,
        };
    } else {
        clock.anchor = None;
        clock.status = TimeSync {
            checked_at: Utc::now().to_rfc3339(),
            warning: "國家標準時間 NTP 校時失敗，使用本機時間；請檢查 DNS 與 UDP 123 連線".into(),
            attempts,
            ..Default::default()
        };
    }
    clock.status.clone()
}
fn read_clock(clock: &Clock) -> DateTime<Utc> {
    match clock.anchor {
        Some((utc, instant)) if instant.elapsed() <= MAX_AGE => {
            datetime(utc + instant.elapsed().as_secs_f64())
        }
        _ => Utc::now(),
    }
}
pub fn now_utc() -> DateTime<Utc> {
    read_clock(&clock().lock().unwrap())
}

pub fn status() -> TimeSync {
    let clock = clock().lock().unwrap();
    let mut status = clock.status.clone();
    if clock
        .anchor
        .is_some_and(|(_, instant)| instant.elapsed() > MAX_AGE)
    {
        status.source = "system".into();
        status.warning = "NTP 校時已超過 30 分鐘，使用本機時間".into();
    }
    status
}

#[cfg(test)]
mod tests {
    use super::*;
    fn exchange() -> ([u8; 48], [u8; 48]) {
        let mut request = [0; 48];
        request[0] = 0x23;
        request[40..].copy_from_slice(&encode(1_700_000_000.0));
        let mut reply = [0; 48];
        reply[0] = 0x24;
        reply[1] = 2;
        reply[24..32].copy_from_slice(&request[40..]);
        reply[32..40].copy_from_slice(&encode(1_700_000_000.25));
        reply[40..48].copy_from_slice(&encode(1_700_000_000.30));
        (request, reply)
    }
    #[test]
    fn validates_exchange_and_computes_offset_and_delay() {
        let (request, reply) = exchange();
        let (offset, delay) =
            parse_reply(&reply, &request, 1_700_000_000.0, 1_700_000_000.1).unwrap();
        assert!((offset - 0.225).abs() < 1e-6);
        assert!((delay - 0.05).abs() < 1e-6);
    }
    #[test]
    fn rejects_invalid_mode_unsynced_origin_and_kiss_of_death() {
        for (position, value) in [(0, 0xe4), (0, 0x23), (0, 0x14), (1, 0), (1, 16), (24, 0)] {
            let (request, mut reply) = exchange();
            reply[position] = value;
            assert!(parse_reply(&reply, &request, 1_700_000_000.0, 1_700_000_000.1).is_err());
        }
        let (request, reply) = exchange();
        assert!(parse_reply(&reply[..47], &request, 0.0, 1.0).is_err());
        assert!(parse_reply(&reply, &request, 1_700_000_000.0, 1_700_000_003.0).is_err());
    }
    #[test]
    fn unfolds_2036_timestamp_rollover() {
        let utc = 2_208_988_800.0;
        assert_eq!(timestamp(&encode(utc), utc), utc);
    }
    #[test]
    fn calibrated_clock_advances_and_expired_samples_fall_back() {
        let mut state = Clock {
            anchor: Some((1_700_000_000.0, Instant::now() - Duration::from_secs(500))),
            ..Default::default()
        };
        assert_eq!(read_clock(&state).timestamp(), 1_700_000_500);
        state.anchor = Some((1_700_000_000.0, Instant::now() - Duration::from_secs(1900)));
        assert!((read_clock(&state) - Utc::now()).num_seconds().abs() < 1);
    }
}
