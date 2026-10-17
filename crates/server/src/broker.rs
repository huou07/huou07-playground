//! Owner-approved, single-use worker operations. Called under the helper policy lock.
use crate::helper;
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use std::fs::{self, Metadata};
use std::io::{Read, Write};
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};
use std::sync::mpsc;
use std::time::{Duration, Instant};

type Result<T> = std::result::Result<T, String>;
const READ_LIMIT: u64 = 1024 * 1024;
const WRITE_LIMIT: usize = 64 * 1024;
const OUTPUT_LIMIT: u64 = 2 * 1024 * 1024;
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

/// Explicit column names keep old metadata queries from returning approved contents.
pub(crate) fn migrate(c: &Connection) -> Result<()> {
    let present = {
        let mut q = c.prepare("PRAGMA table_info(approvals)").map_err(err)?;
        let names = q
            .query_map([], |row| row.get::<_, String>(1))
            .map_err(err)?;
        names
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(err)?
    };
    if !present.iter().any(|name| name == "payload") {
        c.execute("ALTER TABLE approvals ADD COLUMN payload BLOB", [])
            .map_err(err)?;
    }
    // Legacy read approvals did not bind ctime or parent identities; request anew.
    c.execute(
        "UPDATE approvals SET state='invalidated' WHERE payload IS NULL AND state IN ('pending','approved')",
        [],
    )
    .map_err(err)?;
    c.execute(
        "UPDATE approvals SET payload=NULL WHERE payload IS NOT NULL AND (state NOT IN ('pending','approved') OR expires<=?1)",
        [crate::now()],
    ).map_err(err)?;
    Ok(())
}

fn valid_path(text: &str) -> Result<&Path> {
    let path = Path::new(text);
    if text.len() > 4096
        || text.chars().any(char::is_control)
        || (text.len() > 1 && text.ends_with('/'))
        || !path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::RootDir | Component::Normal(_)))
    {
        return Err("Use an absolute target without traversal or control characters".into());
    }
    Ok(path)
}

fn canonical(path: &Path) -> Result<()> {
    let resolved = fs::canonicalize(path).map_err(|_| "Target is unavailable")?;
    if resolved.as_os_str() != path.as_os_str() {
        return Err("Symlink and noncanonical target aliases are unsupported".into());
    }
    Ok(())
}

fn blocked(policy: &Value, worker: &str, path: &Path, operation: &str) -> bool {
    policy["rules"].as_array().is_some_and(|rules| {
        rules.iter().any(|rule| {
            if rule["action"] != "block"
                || rule["expires_at"]
                    .as_u64()
                    .is_some_and(|at| at <= crate::now())
                || !["*", worker].contains(&rule["worker"].as_str().unwrap_or("*"))
                || !rule["operations"]
                    .as_array()
                    .is_some_and(|ops| ops.iter().any(|op| op == operation))
            {
                return false;
            }
            let Some(target) = rule["target"].as_str().map(Path::new) else {
                return true;
            };
            target == path
                || (path.starts_with(target) && (rule["recursive"] == true || target.is_dir()))
        })
    })
}

fn authorize(policy: &Value, worker: &str, path: &Path, operation: &str) -> Result<()> {
    if helper::protected(path, false) {
        return Err("Owner administration, native credentials and NAS are never brokerable".into());
    }
    let revision = policy["revision"]
        .as_u64()
        .ok_or("Invalid policy revision")?;
    if policy["enforced_revision"].as_u64() != Some(revision) {
        return Err("Policy enforcement is pending; broker access is denied".into());
    }
    let setting = helper::worker_setting(policy, worker);
    if setting["enabled"] == false {
        return Err("This managed worker is disabled".into());
    }
    let preset = setting["preset"]
        .as_str()
        .ok_or("Missing security preset")?;
    if !["strict", "balance", "minimal", "none"].contains(&preset) {
        return Err("Unknown security preset".into());
    }
    if preset == "strict" {
        let workspace = valid_path(setting["workspace"].as_str().ok_or("Missing workspace")?)?;
        if !path.starts_with(workspace) {
            return Err("Strict denies outside-workspace broker requests".into());
        }
    }
    if blocked(policy, worker, path, operation) {
        return Err("An active Block takes precedence over owner approval".into());
    }
    Ok(())
}

fn identity(payload: &mut Value, metadata: &Metadata, parent: bool) {
    for (name, value) in [
        ("dev", json!(metadata.dev())),
        ("ino", json!(metadata.ino())),
        ("ctime", json!(metadata.ctime())),
        ("ctime_nsec", json!(metadata.ctime_nsec())),
    ] {
        let key = format!("expected_{}{name}", if parent { "parent_" } else { "" });
        payload[&key] = value;
    }
}

fn same_identity(saved: &Value, fresh: &Value, parent: bool) -> bool {
    ["dev", "ino", "ctime", "ctime_nsec"].iter().all(|name| {
        let key = format!("expected_{}{name}", if parent { "parent_" } else { "" });
        !saved[&key].is_null() && saved[&key] == fresh[&key]
    })
}

fn snapshot(path: &Path, operation: &str) -> Result<Value> {
    let owner = crate::user_ids("huou07")?.0;
    let mut payload = json!({"version":1});
    if operation == "create" || operation == "delete" {
        let parent = path.parent().ok_or("Target has no parent")?;
        canonical(parent)?;
        let metadata = fs::symlink_metadata(parent).map_err(|_| "Parent is unavailable")?;
        if !metadata.is_dir() || metadata.uid() != owner {
            return Err("Create/delete requires an ordinary owner-owned parent directory".into());
        }
        identity(&mut payload, &metadata, true);
    }
    if operation == "create" {
        match fs::symlink_metadata(path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(payload),
            _ => {
                return Err(
                    "Create requires a nonexistent destination; overwrites are unsupported".into(),
                )
            }
        }
    }
    canonical(path)?;
    let metadata = fs::symlink_metadata(path).map_err(|_| "Target is unavailable")?;
    if metadata.uid() != owner
        || metadata.file_type().is_symlink()
        || if operation == "list" {
            !metadata.is_dir()
        } else {
            !metadata.is_file() || metadata.nlink() != 1
        }
    {
        return Err(
            "Select an ordinary owner-owned object without symlink or hardlink aliases".into(),
        );
    }
    if operation == "read" && metadata.len() > READ_LIMIT {
        return Err("A broker read is limited to one file of at most 1 MiB".into());
    }
    identity(&mut payload, &metadata, false);
    Ok(payload)
}

/// The actor runs as the owner, not root; bound its output and lifetime.
fn actor(request: &Value) -> Result<Vec<u8>> {
    let mut child = helper::actor(request)?;
    let mut stdin = child.stdin.take().ok_or("Actor stdin unavailable")?;
    if writeln!(stdin, "{request}").is_err() {
        let _ = child.kill();
        let _ = child.wait();
        return Err("Broker file request failed".into());
    }
    drop(stdin);
    let stdout = child.stdout.take().ok_or("Actor stdout unavailable")?;
    let (send, receive) = mpsc::channel();
    std::thread::spawn(move || {
        let mut bytes = Vec::new();
        let result = stdout.take(OUTPUT_LIMIT + 1).read_to_end(&mut bytes);
        let _ = send.send(result.map(|_| bytes).map_err(err));
    });
    let deadline = Instant::now() + Duration::from_secs(30);
    let output = loop {
        match receive.recv_timeout(Duration::from_millis(20)) {
            Ok(output) => break output,
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                break Err("Broker actor output failed".into())
            }
            Err(mpsc::RecvTimeoutError::Timeout) if Instant::now() < deadline => {}
            Err(_) => break Err("Broker actor timed out; approval remains consumed".into()),
        }
    };
    let output = match output {
        Ok(bytes) if bytes.len() as u64 <= OUTPUT_LIMIT => bytes,
        Ok(_) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("Broker actor response exceeded its limit".into());
        }
        Err(error) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    loop {
        match child.try_wait().map_err(err)? {
            Some(status) if status.success() => return Ok(output),
            Some(_) => return Err(actor_error(&output)),
            None if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(10)),
            None => {
                let _ = child.kill();
                let _ = child.wait();
                return Err("Broker actor timed out; approval remains consumed".into());
            }
        }
    }
}

fn actor_error(bytes: &[u8]) -> String {
    serde_json::from_slice::<Value>(bytes)
        .ok()
        .and_then(|v| v["error"].as_str().map(str::to_owned))
        .unwrap_or_else(|| "Approved object is no longer available; request a new approval".into())
}

fn actor_result(bytes: &[u8]) -> Result<Value> {
    let envelope: Value =
        serde_json::from_slice(bytes).map_err(|_| "Invalid broker actor response")?;
    if envelope["ok"] != true {
        return Err(actor_error(bytes));
    }
    Ok(envelope["data"].clone())
}

pub(crate) fn request(uid: u32, value: &Value) -> Result<Value> {
    let worker = helper::workers()
        .into_iter()
        .find(|name| crate::user_ids(name).is_ok_and(|id| id.0 == uid))
        .ok_or("Unknown worker principal")?;
    let policy = helper::load()?;
    let c = helper::db()?;
    match value["op"].as_str() {
        Some("request") => {
            let operation = value["operation"].as_str().ok_or("Missing operation")?;
            if !["list", "read", "write", "create", "delete"].contains(&operation) {
                return Err(
                    "Broker supports list/read/write/create/delete; execute is unsupported".into(),
                );
            }
            let path = valid_path(value["path"].as_str().ok_or("Missing target")?)?;
            authorize(&policy, worker, path, operation)?;
            let mut payload = snapshot(path, operation)?;
            if operation == "write" || operation == "create" {
                let content = value["content"]
                    .as_str()
                    .ok_or("Provide the exact UTF-8 content to approve")?;
                if content.len() > WRITE_LIMIT {
                    return Err("Approved write/create payload exceeds 64 KiB".into());
                }
                payload["content"] = content.into();
            } else if !value["content"].is_null() {
                return Err("Content payload is accepted only for write/create".into());
            }
            if serde_json::to_vec(&payload).map_err(err)?.len() > 110 * 1024 {
                return Err("Approved content exceeds the encoded broker transport limit".into());
            }
            let id = crate::random_token()?;
            let expires = crate::now() + 300;
            let (dev, ino) = if operation == "create" {
                (
                    &payload["expected_parent_dev"],
                    &payload["expected_parent_ino"],
                )
            } else {
                (&payload["expected_dev"], &payload["expected_ino"])
            };
            c.execute(
                "INSERT INTO approvals(id,worker,path,operation,revision,expires,state,dev,ino,payload) VALUES(?1,?2,?3,?4,?5,?6,'pending',?7,?8,?9)",
                params![id, worker, path.to_string_lossy(), operation, policy["revision"].as_u64().unwrap(), expires, dev.as_u64(), ino.as_u64(), serde_json::to_vec(&payload).map_err(err)?],
            ).map_err(err)?;
            helper::audit(
                &c,
                "Worker requested one scoped broker operation; owner decision required",
            )?;
            Ok(
                json!({"id":id,"state":"pending","operation":operation,"expires_at":expires,"revision":policy["revision"]}),
            )
        }
        Some("redeem") => redeem(&c, &policy, worker, value),
        _ => Err("Unknown broker operation".into()),
    }
}

fn redeem(c: &Connection, policy: &Value, worker: &str, value: &Value) -> Result<Value> {
    let id = value["id"]
        .as_str()
        .filter(|id| id.len() == 64)
        .ok_or("Invalid approval id")?;
    let revision = policy["revision"]
        .as_u64()
        .ok_or("Invalid policy revision")?;
    let (path, operation, bytes) = c.query_row(
        "SELECT path,operation,payload FROM approvals WHERE id=?1 AND worker=?2 AND state='approved' AND expires>?3 AND revision=?4",
        params![id, worker, crate::now(), revision],
        |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, Vec<u8>>(2)?)),
    ).map_err(|_| "Approval pending, denied, expired, stale, or already used")?;
    if !["list", "read", "write", "create", "delete"].contains(&operation.as_str()) {
        return Err("Stored approval operation is unsupported".into());
    }
    let path = valid_path(&path)?;
    authorize(policy, worker, path, &operation)?;
    let payload: Value = serde_json::from_slice(&bytes).map_err(|_| "Invalid stored approval")?;
    if payload["version"] != 1 {
        return Err("Stored approval version is unsupported".into());
    }
    let fresh = snapshot(path, &operation)?;
    if (operation != "create" && !same_identity(&payload, &fresh, false))
        || (["create", "delete"].contains(&operation.as_str())
            && !same_identity(&payload, &fresh, true))
    {
        return Err("Approved file or parent changed; request a new approval".into());
    }
    let mut request = payload;
    request["area"] = "storage".into();
    request["path"] = path.to_string_lossy().as_ref().into();
    request["op"] = if operation == "read" {
        "fs_read".into()
    } else {
        format!("fs_broker_{operation}").into()
    };
    request["length"] = READ_LIMIT.into();
    request["limit"] = 500.into();
    // Consume before any side effect. A failed attempt cannot replay a partial write.
    let consumed = c.execute(
        "UPDATE approvals SET state='used',payload=NULL WHERE id=?1 AND worker=?2 AND state='approved' AND revision=?3 AND expires>?4",
        params![id, worker, revision, crate::now()],
    ).map_err(err)?;
    if consumed != 1 {
        return Err("Approval was consumed, expired, or revoked".into());
    }
    helper::audit(
        c,
        "Worker consumed one single-use approved broker operation",
    )?;
    let output = actor(&request)?;
    if operation == "read" {
        let split = output
            .iter()
            .position(|byte| *byte == b'\n')
            .ok_or("Invalid broker read response")?
            + 1;
        let meta = actor_result(&output[..split])?;
        let contents = &output[split..];
        if contents.len() as u64 > READ_LIMIT
            || meta["length"].as_u64() != Some(contents.len() as u64)
        {
            return Err("Broker read was incomplete or exceeded its byte limit".into());
        }
        let (data, encoding) = match std::str::from_utf8(contents) {
            Ok(text) => (text.to_owned(), "utf-8"),
            Err(_) => {
                use std::fmt::Write as _;
                let mut hex = String::with_capacity(contents.len() * 2);
                for byte in contents {
                    let _ = write!(&mut hex, "{byte:02x}");
                }
                (hex, "hex")
            }
        };
        return Ok(json!({"data":data,"encoding":encoding,"bytes":contents.len(),"state":"used"}));
    }
    let data = actor_result(&output)?;
    if operation == "list" {
        let entries = data["entries"].as_array().ok_or("Invalid broker listing")?;
        let mut visible = Vec::new();
        for entry in entries.iter().take(500) {
            let Some(name) = entry["name"].as_str() else {
                continue;
            };
            if name.is_empty()
                || name == "."
                || name == ".."
                || name.contains('/')
                || name.chars().any(char::is_control)
            {
                continue;
            }
            let child: PathBuf = path.join(name);
            if helper::protected(&child, false)
                || blocked(policy, worker, &child, "list")
                || blocked(policy, worker, &child, "read")
            {
                continue;
            }
            visible.push(json!({"name":name,"kind":entry["kind"],"size":entry["size"],"modified":entry["modified"]}));
        }
        return Ok(
            json!({"entries":visible,"partial":data["total"].as_u64().is_some_and(|total|total>entries.len() as u64),"state":"used"}),
        );
    }
    // Never echo the approved content back through administration or mutation results.
    Ok(json!({"ok":true,"operation":operation,"state":"used"}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migration_is_idempotent_and_invalidates_unbound_legacy_approvals() {
        let c = Connection::open_in_memory().unwrap();
        c.execute_batch("CREATE TABLE approvals(id TEXT PRIMARY KEY,worker TEXT,path TEXT,operation TEXT,revision INTEGER,expires INTEGER,state TEXT,dev INTEGER,ino INTEGER);
            INSERT INTO approvals VALUES('legacy','fixture','/fixture','read',0,9999999999,'approved',1,2);").unwrap();
        migrate(&c).unwrap();
        migrate(&c).unwrap();
        let (state, payload): (String, Option<Vec<u8>>) = c
            .query_row(
                "SELECT state,payload FROM approvals WHERE id='legacy'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap();
        assert_eq!(state, "invalidated");
        assert!(payload.is_none());
    }

    #[test]
    fn strict_and_active_blocks_cannot_be_overridden_by_an_approval() {
        let policy = json!({"revision":2,"enforced_revision":2,"preset":"strict",
            "workspace":"/tmp/fixture-workspace","rules":[{"action":"block","worker":"*",
            "target":"/tmp/fixture-workspace/private","recursive":true,"operations":["read"]}]});
        assert!(authorize(&policy, "fixture", Path::new("/tmp/outside"), "read").is_err());
        assert!(authorize(
            &policy,
            "fixture",
            Path::new("/tmp/fixture-workspace/private/file"),
            "read"
        )
        .is_err());
        assert!(authorize(
            &policy,
            "fixture",
            Path::new("/tmp/fixture-workspace/public"),
            "read"
        )
        .is_ok());
        assert!(authorize(&policy, "fixture", Path::new("/etc/passwd"), "read").is_err());
    }

    #[test]
    fn malformed_paths_and_incomplete_object_bindings_are_rejected() {
        assert!(valid_path("relative").is_err());
        assert!(valid_path("/tmp/../private").is_err());
        assert!(valid_path("/tmp/file\nname").is_err());
        let bound =
            json!({"expected_dev":1,"expected_ino":2,"expected_ctime":3,"expected_ctime_nsec":4});
        assert!(same_identity(&bound, &bound, false));
        let mut changed = bound.clone();
        changed["expected_ctime_nsec"] = 5.into();
        assert!(!same_identity(&bound, &changed, false));
        assert!(!same_identity(&json!({}), &json!({}), false));
    }
}
#[test]
fn individual_worker_settings_apply_to_broker_authorization() {
    let policy = json!({"revision":2,"enforced_revision":2,"preset":"none","workspace":"/home/huou07/Projects","rules":[],"worker_settings":{"dsh-worker":{"preset":"strict"},"codex-worker":{"enabled":false}}});
    assert!(authorize(&policy, "dsh-worker", Path::new("/tmp/ordinary"), "read").is_err());
    assert!(authorize(
        &policy,
        "opencode-worker",
        Path::new("/tmp/ordinary"),
        "read"
    )
    .is_ok());
    assert!(authorize(
        &policy,
        "codex-worker",
        Path::new("/home/huou07/Projects/ordinary"),
        "read"
    )
    .is_err());
}
