//! Fixed harness catalog and owner-reviewed, serialized account maintenance jobs.
use serde_json::{json, Value};
use std::{
    fs,
    os::unix::fs::MetadataExt,
    sync::{Arc, Mutex, OnceLock},
};
fn job() -> &'static Mutex<Value> {
    static JOB: OnceLock<Mutex<Value>> = OnceLock::new();
    JOB.get_or_init(|| Mutex::new(json!({"state":"idle"})))
}
/// Root of the protected pre-worker ACL snapshot registry.
fn acl_baseline_root() -> std::path::PathBuf {
    std::env::var("H07P_ACL_BACKUP_ROOT")
        .ok()
        .filter(|value| !value.is_empty())
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| std::path::PathBuf::from("/var/backups/h07p-harness-workers"))
}

/// The account adapter writes `YYYYMMDD-HHMMSS[-<extra>]` snapshot directories.
/// Reject any other name so an unrelated directory cannot be selected.
fn acl_baseline_snapshot_name(name: &str) -> bool {
    let bytes = name.as_bytes();
    let Some(head) = bytes.get(..15) else {
        return false;
    };
    let stamped = head
        .get(..8)
        .is_some_and(|part| part.iter().all(u8::is_ascii_digit))
        && head.get(8) == Some(&b'-')
        && head
            .get(9..15)
            .is_some_and(|part| part.iter().all(u8::is_ascii_digit));
    stamped && matches!(bytes.get(15), None | Some(&b'-'))
}

/// A snapshot is usable only when the file and its directory are regular,
/// owned by the expected account and not writable by group or other.
fn valid_acl_baseline(path: &std::path::Path, expected_uid: u32) -> bool {
    let Ok(meta) = fs::symlink_metadata(path) else {
        return false;
    };
    if !meta.is_file() || meta.uid() != expected_uid || meta.mode() & 0o022 != 0 {
        return false;
    }
    if !(1_000_000..=500 * 1024 * 1024).contains(&meta.len()) {
        return false;
    }
    let Some(parent) = path.parent() else {
        return false;
    };
    let Ok(parent_meta) = fs::symlink_metadata(parent) else {
        return false;
    };
    if !parent_meta.is_dir() || parent_meta.uid() != expected_uid || parent_meta.mode() & 0o022 != 0
    {
        return false;
    }
    parent
        .file_name()
        .and_then(std::ffi::OsStr::to_str)
        .is_some_and(acl_baseline_snapshot_name)
}

/// Newest validated snapshot under `root`, or `None` when none qualifies.
///
/// Ordering uses the full modification time — seconds *and* the fractional
/// nanosecond component, which is all `mtime_nsec` provides — and then the
/// timestamped directory name. Seconds alone is too coarse: the adapter can
/// write two snapshots inside one second, and the registry must still pick the
/// same one every time rather than following directory iteration order.
fn select_acl_baseline_in(root: &std::path::Path, expected_uid: u32) -> Option<std::path::PathBuf> {
    let mut best: Option<((i64, i64), String, std::path::PathBuf)> = None;
    for entry in fs::read_dir(root).ok()?.flatten() {
        let candidate = entry.path().join("acl.restore");
        if !valid_acl_baseline(&candidate, expected_uid) {
            continue;
        }
        let Ok(meta) = fs::symlink_metadata(&candidate) else {
            continue;
        };
        let stamp = (meta.mtime(), meta.mtime_nsec());
        let name = entry.file_name().to_string_lossy().to_string();
        let newer = match &best {
            None => true,
            Some((when, previous, _)) => (stamp, &name) > (*when, previous),
        };
        if newer {
            best = Some((stamp, name, candidate));
        }
    }
    best.map(|(_, _, path)| path)
}

fn select_acl_baseline() -> Option<std::path::PathBuf> {
    select_acl_baseline_in(&acl_baseline_root(), 0)
}

pub fn catalog() -> Result<Value, String> {
    let policy = crate::helper::load()?;
    let passwd = fs::read_to_string("/etc/passwd").map_err(|_| "Account metadata unavailable")?;
    let workers:Vec<_>=crate::helper::workers().iter().map(|name|{
        let harness=name.trim_end_matches("-worker");
        let executable=match harness {"dsh"=>"/home/huou07/.local/bin/dsh","codex"=>"/home/huou07/.local/bin/codex",_=>"/home/huou07/.local/bin/opencode"};
        let fields=passwd.lines().find_map(|line|{let fields:Vec<_>=line.split(':').collect();(fields.len()==7&&fields[0]==*name).then_some(fields)});
        let account=crate::user_ids(name).ok();
        let setting=crate::helper::worker_setting(&policy,name);
        json!({"name":name,"harness":harness,"detected":fs::metadata(executable).map(|m|{use std::os::unix::fs::PermissionsExt;m.is_file()&&m.permissions().mode()&0o111!=0}).unwrap_or(false),"account_exists":account.is_some(),"uid":account.map(|a|a.0),"home":fields.as_ref().map(|f|f[5]),"preset":setting["preset"],"workspace":setting["workspace"],"enabled":setting["enabled"]})
    }).collect();
    let baseline = select_acl_baseline();
    let acl_reset_available = baseline.is_some();
    let acl_baseline = baseline
        .as_deref()
        .and_then(std::path::Path::parent)
        .and_then(std::path::Path::file_name)
        .and_then(std::ffi::OsStr::to_str)
        .map(str::to_owned);
    Ok(
        json!({"workers":workers,"revision":policy["revision"],"job":job().lock().unwrap_or_else(|e|e.into_inner()).clone(),"acl_reset_available":acl_reset_available,"acl_baseline":acl_baseline,"note":"Detects supported installed harness executables without running them. Shared apps/home are reused. Removal retains shared data and a locked retired UID to prevent permission reuse."}),
    )
}
pub fn control(op: &str, v: &Value, lock: Arc<Mutex<()>>) -> Result<Value, String> {
    match op {
        "worker_setup_status" => catalog(),
        "worker_setup_job" => {
            let mut status = job().lock().unwrap_or_else(|e| e.into_inner()).clone();
            if let Ok(bytes) = fs::read(crate::helper::dir().join("worker-progress.json")) {
                if bytes.len() <= 4096 {
                    if let Ok(progress) = serde_json::from_slice::<Value>(&bytes) {
                        if progress["id"] == status["id"] {
                            status["progress"] = progress;
                        }
                    }
                }
            }
            Ok(status)
        }
        "worker_setup_run" => {
            let action = v["action"].as_str().ok_or("Select a worker action")?;
            if !["create", "repair", "remove", "start-web", "reset-acl"].contains(&action) {
                return Err("Unsupported worker action".into());
            }
            let workers = v["workers"]
                .as_array()
                .filter(|s| !s.is_empty() && s.len() <= 3)
                .ok_or("Select one or more supported workers")?;
            let mut unique = std::collections::BTreeSet::new();
            for worker in workers {
                let name = worker.as_str().ok_or("Invalid worker")?;
                if !crate::helper::workers().contains(&name) || !unique.insert(name) {
                    return Err("Choose distinct supported worker accounts".into());
                }
            }
            if action == "reset-acl" && unique.len() != crate::helper::workers().len() {
                return Err(
                    "ACL reset requires all supported worker identities to be selected".into(),
                );
            }
            if v["confirmed"] != true {
                return Err("Review and confirm the selected account changes".into());
            }
            let id = crate::random_token()?;
            let mut current = job().lock().unwrap_or_else(|e| e.into_inner());
            if current["state"] == "running" {
                return Err("Worker maintenance is already running. Wait for its result.".into());
            }
            *current = json!({"id":id,"state":"running","action":action,"workers":workers,"started_at":crate::now()});
            let mut request = v.clone();
            request["job_id"] = json!(id);
            let job_id = id.clone();
            std::thread::spawn(move || {
                let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
                let result = crate::helper::maintain_workers(&request);
                let mut record = job().lock().unwrap_or_else(|e| e.into_inner());
                record["state"] = json!(if result.is_ok() {
                    "completed"
                } else {
                    "failed"
                });
                record["finished_at"] = json!(crate::now());
                record["result"] = match result {
                    Ok(value) => value,
                    Err(error) => json!({"error":error}),
                };
                record["id"] = json!(job_id);
            });
            Ok(current.clone())
        }
        _ => Err("Unknown worker setup operation".into()),
    }
}
pub(crate) fn driver(action: &str, workers: &[Value], job_id: &str) -> Result<(), String> {
    let path = std::env::var("H07P_WORKER_SETUP")
        .unwrap_or_else(|_| "/usr/lib/huou07-playground/workers.py".into());
    let metadata = fs::symlink_metadata(&path)
        .map_err(|_| "Worker setup adapter is missing. Repair the installed package.")?;
    use std::os::unix::fs::MetadataExt;
    if !metadata.is_file() || metadata.uid() != 0 || metadata.mode() & 0o022 != 0 {
        return Err("Worker setup adapter must be root-owned and protected".into());
    }
    for parent in std::path::Path::new(&path).ancestors().skip(1) {
        let m =
            fs::symlink_metadata(parent).map_err(|_| "Cannot verify worker setup installation")?;
        if !m.is_dir() || m.uid() != 0 || m.mode() & 0o022 != 0 {
            return Err("Worker setup adapter has an unprotected ancestor".into());
        }
    }
    let control = crate::helper::dir();
    let control = control.to_str().ok_or("Invalid control path")?;
    let mut arguments = vec![
        path.as_str(),
        action,
        "--control-dir",
        control,
        "--job-id",
        job_id,
    ];
    for worker in workers {
        arguments.push(worker.as_str().ok_or("Invalid worker")?);
    }
    crate::telemetry::command("/usr/bin/python3",&arguments,900).ok_or_else(||"Account/ACL setup failed or exceeded its bound. Affected workers remain stopped; use Repair and inspect the protected ACL backup.".into()).map(|_|())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    fn scratch(tag: &str) -> std::path::PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|elapsed| elapsed.as_nanos())
            .unwrap_or(0);
        let root =
            std::env::temp_dir().join(format!("h07p-acl-{tag}-{}-{unique}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        root
    }

    fn snapshot(root: &std::path::Path, name: &str, mode: u32, size: u64) -> std::path::PathBuf {
        let directory = root.join(name);
        fs::create_dir_all(&directory).unwrap();
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
        let file = directory.join("acl.restore");
        fs::File::create(&file).unwrap().set_len(size).unwrap();
        fs::set_permissions(&file, fs::Permissions::from_mode(mode)).unwrap();
        file
    }

    #[test]
    fn accepts_legacy_and_nanosecond_snapshot_names() {
        assert!(acl_baseline_snapshot_name("20261015-220803"));
        assert!(acl_baseline_snapshot_name("20261017-120000-123456789"));
        assert!(!acl_baseline_snapshot_name("not-a-stamp"));
        assert!(!acl_baseline_snapshot_name("2026-1015-220803"));
        assert!(!acl_baseline_snapshot_name("20261015-220803x"));
    }

    #[test]
    fn selects_newest_validated_snapshot() {
        let root = scratch("select");
        let uid = fs::metadata(&root).unwrap().uid();
        let older = snapshot(&root, "20261001-000000-1", 0o600, 1_100_000);
        // Written back to back: a seconds-resolution mtime cannot order these,
        // so the timestamped name must break the tie deterministically.
        let newer = snapshot(&root, "20261015-220803", 0o600, 1_100_000);
        let selected = select_acl_baseline_in(&root, uid);
        assert_eq!(selected.as_deref(), Some(newer.as_path()));
        assert_ne!(selected.as_deref(), Some(older.as_path()));
        assert_eq!(
            select_acl_baseline_in(&root, uid).as_deref(),
            selected.as_deref()
        );
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn a_later_snapshot_wins_even_when_names_sort_early() {
        let root = scratch("recency");
        let uid = fs::metadata(&root).unwrap().uid();
        // Same timestamped prefix, one directory per second: mtime decides.
        let first = snapshot(&root, "20261015-220803", 0o600, 1_100_000);
        std::thread::sleep(Duration::from_millis(1100));
        let second = snapshot(&root, "20261015-220700", 0o600, 1_100_000);
        let selected = select_acl_baseline_in(&root, uid);
        assert_eq!(selected.as_deref(), Some(second.as_path()));
        assert_ne!(selected.as_deref(), Some(first.as_path()));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn rejects_untrusted_or_unnamed_snapshots() {
        let root = scratch("reject");
        let uid = fs::metadata(&root).unwrap().uid();
        let world_writable = snapshot(&root, "20261010-101010-1", 0o600, 1_100_000);
        fs::set_permissions(
            world_writable.parent().unwrap(),
            fs::Permissions::from_mode(0o777),
        )
        .unwrap();
        snapshot(&root, "unrelated", 0o600, 1_100_000);
        snapshot(&root, "20261011-101010-1", 0o600, 10);
        snapshot(&root, "20261012-101010-1", 0o666, 1_100_000);
        assert!(select_acl_baseline_in(&root, uid).is_none());
        let _ = fs::remove_dir_all(&root);
    }
}
