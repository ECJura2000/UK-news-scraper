use anyhow::{Context, Result};
use chrono::Utc;
use fs2::FileExt;
use serde_json::{json, Map, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

fn default_registry() -> PathBuf {
    dirs_path().join(".codex/automations/uk/sent_run_ids.json")
}
fn dirs_path() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}
struct Lock(File);
impl Drop for Lock {
    fn drop(&mut self) {
        let _ = self.0.unlock();
    }
}
fn lock(path: &Path) -> Result<Lock> {
    if let Some(p) = path.parent() {
        fs::create_dir_all(p)?
    }
    let file = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path)?;
    file.lock_exclusive()?;
    Ok(Lock(file))
}
fn read(path: &Path) -> Result<Map<String, Value>> {
    if !path.exists() {
        return Ok(Map::new());
    }
    serde_json::from_str::<Value>(&fs::read_to_string(path)?)?
        .as_object()
        .cloned()
        .context("delivery registry must be an object")
}
fn write(path: &Path, map: &Map<String, Value>) -> Result<()> {
    if let Some(p) = path.parent() {
        fs::create_dir_all(p)?
    }
    let tmp = path.with_extension("json.tmp");
    let mut f = File::create(&tmp)?;
    f.write_all(serde_json::to_string_pretty(map)?.as_bytes())?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    fs::rename(tmp, path)?;
    Ok(())
}
pub fn claim(summary: &Path, registry: Option<&Path>) -> Result<Value> {
    let s: Value = serde_json::from_str(&fs::read_to_string(summary)?)?;
    for k in [
        "delivery_id",
        "run_id",
        "status",
        "data_fingerprint",
        "output_file",
    ] {
        if s.get(k)
            .and_then(Value::as_str)
            .filter(|x| !x.is_empty())
            .is_none()
        {
            anyhow::bail!("run summary 缺少欄位：{k}")
        }
    }
    let path = registry.map(Into::into).unwrap_or_else(default_registry);
    let _lock = lock(&path.with_extension("lock"))?;
    let mut map = read(&path)?;
    let id = s["delivery_id"].as_str().unwrap();
    let run = s["run_id"].as_str().unwrap();
    if let Some(existing) = map.get(run) {
        return Ok(
            json!({"claimed":false,"delivery_id":id,"existing":existing,"reason":"legacy run_id already sent"}),
        );
    }
    if let Some(existing) = map.get(id) {
        if matches!(
            existing.get("state").and_then(Value::as_str),
            Some("claimed" | "sent")
        ) {
            return Ok(json!({"claimed":false,"delivery_id":id,"existing":existing}));
        }
    }
    map.insert(id.into(),json!({"state":"claimed","run_id":run,"status":s["status"],"data_fingerprint":s["data_fingerprint"],"claimed_at":Utc::now().to_rfc3339(),"excel_path":s["output_file"],"message_id":"","sent_at":""}));
    write(&path, &map)?;
    Ok(json!({"claimed":true,"delivery_id":id}))
}
pub fn complete(id: &str, message: &str, registry: Option<&Path>) -> Result<Value> {
    let path = registry.map(Into::into).unwrap_or_else(default_registry);
    let _lock = lock(&path.with_extension("lock"))?;
    let mut map = read(&path)?;
    let item = map
        .get_mut(id)
        .and_then(Value::as_object_mut)
        .context(format!("delivery 尚未 claim：{id}"))?;
    if item.get("state").and_then(Value::as_str) != Some("claimed") {
        anyhow::bail!("delivery 尚未 claim：{id}")
    }
    item.insert("state".into(), json!("sent"));
    item.insert("message_id".into(), json!(message));
    item.insert("sent_at".into(), json!(Utc::now().to_rfc3339()));
    let result = Value::Object(item.clone());
    write(&path, &map)?;
    Ok(result)
}
pub fn release(id: &str, registry: Option<&Path>) -> Result<bool> {
    let path = registry.map(Into::into).unwrap_or_else(default_registry);
    let _lock = lock(&path.with_extension("lock"))?;
    let mut map = read(&path)?;
    let release = map
        .get(id)
        .and_then(|x| x.get("state"))
        .and_then(Value::as_str)
        == Some("claimed");
    if release {
        map.remove(id);
        write(&path, &map)?
    }
    Ok(release)
}
pub fn status(id: Option<&str>, state: Option<&str>, registry: Option<&Path>) -> Result<Value> {
    let path = registry.map(Into::into).unwrap_or_else(default_registry);
    let map = read(&path)?;
    if let Some(id) = id {
        return Ok(json!({"delivery_id":id,"record":map.get(id)}));
    }
    let records = map
        .into_iter()
        .filter(|(_, v)| state.is_none() || v.get("state").and_then(Value::as_str) == state)
        .collect::<Map<_, _>>();
    Ok(json!({"count":records.len(),"records":records}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn python_registry_shape_round_trips_claim_complete() {
        let dir = tempdir().unwrap();
        let registry = dir.path().join("sent_run_ids.json");
        let summary = dir.path().join("report.run.json");
        fs::write(&summary, r#"{"delivery_id":"run:complete:abc","run_id":"run","status":"complete","data_fingerprint":"abcdef","output_file":"/tmp/report.xlsx"}"#).unwrap();
        assert_eq!(claim(&summary, Some(&registry)).unwrap()["claimed"], true);
        let record = complete("run:complete:abc", "gmail-123", Some(&registry)).unwrap();
        assert_eq!(record["state"], "sent");
        assert_eq!(record["message_id"], "gmail-123");
        assert!(!release("run:complete:abc", Some(&registry)).unwrap());
    }

    #[test]
    fn release_is_idempotent_for_claimed_record() {
        let dir = tempdir().unwrap();
        let registry = dir.path().join("sent_run_ids.json");
        let summary = dir.path().join("report.run.json");
        fs::write(&summary, r#"{"delivery_id":"run:degraded:def","run_id":"run","status":"degraded","data_fingerprint":"def","output_file":"/tmp/report.xlsx"}"#).unwrap();
        claim(&summary, Some(&registry)).unwrap();
        assert!(release("run:degraded:def", Some(&registry)).unwrap());
        assert!(!release("run:degraded:def", Some(&registry)).unwrap());
    }
}
