//! Credential Guard shares the existing privileged control plane. Content is
//! read by an owner actor; scanner output and original bytes never enter events.
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs::{self, Metadata, OpenOptions},
    io::{Read, Write},
    os::{
        fd::FromRawFd,
        unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    },
    path::{Component, Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex, OnceLock,
    },
    time::{Duration, Instant},
};
type Result<T> = std::result::Result<T, String>;
const LIMIT: usize = 1024 * 1024;
static GENERATION: AtomicU64 = AtomicU64::new(1);
static HEALTH: OnceLock<Mutex<Value>> = OnceLock::new();
fn health() -> &'static Mutex<Value> {
    HEALTH.get_or_init(|| Mutex::new(json!({"state":"STARTING","watches":0,"overflows":0})))
}
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
pub(crate) fn migrate(c: &Connection) -> Result<()> {
    c.execute_batch("CREATE TABLE IF NOT EXISTS guard_config(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS guard_events(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,kind TEXT NOT NULL,path TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS guard_plans(id TEXT PRIMARY KEY,body TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS guard_quarantine(id TEXT PRIMARY KEY,body TEXT NOT NULL);").map_err(err)
}
fn config(c: &Connection) -> Result<Value> {
    let s: Option<String> = c
        .query_row("SELECT body FROM guard_config WHERE id=1", [], |r| r.get(0))
        .optional()
        .map_err(err)?;
    match s {
        Some(s) => serde_json::from_str(&s).map_err(err),
        None => {
            Ok(json!({"revision":0,"enabled":false,"content":false,"scopes":[],"safe_exports":[]}))
        }
    }
}
fn event(c: &Connection, kind: &str, path: &str) -> Result<()> {
    c.execute(
        "INSERT INTO guard_events(at,kind,path) VALUES(?1,?2,?3)",
        params![crate::now(), kind, crate::redact::safe_path(path)],
    )
    .map_err(err)?;
    c.execute(
        "DELETE FROM guard_events WHERE id < (SELECT max(id)-2000 FROM guard_events)",
        [],
    )
    .map_err(err)?;
    Ok(())
}
fn canonical(text: &str) -> Result<PathBuf> {
    let p = Path::new(text);
    if text.len() > 4096
        || !p.is_absolute()
        || text.ends_with('/')
        || crate::redact::safe_path(text) != text
        || p.components()
            .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
    {
        return Err("Use a canonical absolute path without secret-bearing names".into());
    }
    if fs::canonicalize(p)
        .map_err(|_| "Path is unavailable")?
        .as_os_str()
        != p.as_os_str()
    {
        return Err("Path aliases are not supported".into());
    }
    Ok(p.into())
}
fn roots(v: &Value, require_owner: bool) -> Result<Vec<PathBuf>> {
    let list = v
        .as_array()
        .ok_or("Select a list of existing log folders")?;
    if list.len() > 8 {
        return Err("At most eight log folders are supported".into());
    }
    let uid = crate::user_ids("huou07")?.0;
    list.iter().map(|p| {
        let path = canonical(p.as_str().ok_or("Invalid folder")?)?;
        let meta = fs::metadata(&path).map_err(err)?;
        if (require_owner && (crate::helper::protected(&path, true) || meta.uid() != uid))
            || (!require_owner && crate::helper::protected(&path, false))
            || crate::scan::excluded_filesystem(&path)
            || !meta.is_dir()
        {
            return Err(if require_owner {
                "Select an owner-owned log export folder anywhere on the host, outside protected stores".into()
            } else {
                "Select a host folder anywhere on the system, outside protected stores and pseudo-filesystems".into()
            });
        }
        Ok(path)
    }).collect()
}
fn identity(meta: &Metadata) -> Value {
    json!({"dev":meta.dev(),"ino":meta.ino(),"ctime":meta.ctime(),"ctime_nsec":meta.ctime_nsec(),"size":meta.len()})
}
fn staging(path: &Path) -> bool {
    path.file_name().and_then(|s| s.to_str()).is_some_and(|s| {
        s.starts_with(".h07p-replace-")
            || s.starts_with(".h07p-upload-")
            || s.starts_with(".h07p-broker-")
    })
}
fn closed(meta: &Metadata) -> Result<()> {
    let start = Instant::now();
    for process in fs::read_dir("/proc").map_err(|_| "Writer inventory unavailable")? {
        let process = process.map_err(|_| "Writer inventory changed")?;
        if process
            .file_name()
            .to_string_lossy()
            .parse::<u32>()
            .is_err()
        {
            continue;
        }
        let descriptors = match fs::read_dir(process.path().join("fd")) {
            Ok(v) => v,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(_) => return Err("Writer inventory incomplete".into()),
        };
        for fd in descriptors.flatten() {
            if start.elapsed() > Duration::from_secs(2) {
                return Err("Writer inventory exceeded its budget; retry later".into());
            }
            let Ok(m) = fs::metadata(fd.path()) else {
                continue;
            };
            if m.dev() != meta.dev() || m.ino() != meta.ino() {
                continue;
            }
            let flags = fs::read_to_string(process.path().join("fdinfo").join(fd.file_name()))
                .map_err(|_| "Writer state unavailable")?;
            let mode = flags
                .lines()
                .find_map(|l| l.strip_prefix("flags:\t"))
                .and_then(|v| u32::from_str_radix(v, 8).ok())
                .ok_or("Writer state unavailable")?;
            if mode & libc::O_ACCMODE as u32 != libc::O_RDONLY as u32 {
                return Err(
                    "This log is open for writing; export or close it before cleaning".into(),
                );
            }
        }
    }
    Ok(())
}
fn target(c: &Connection, text: &str) -> Result<(PathBuf, Metadata)> {
    let cfg = config(c)?;
    let path = canonical(text)?;
    let allowed = cfg["safe_exports"].as_array().is_some_and(|v| {
        v.iter()
            .filter_map(Value::as_str)
            .any(|r| path.starts_with(r) && path != Path::new(r))
    });
    if !allowed || crate::helper::protected(&path, false) {
        return Err("Register this closed export folder first; native stores and live journals are excluded".into());
    }
    let m = fs::metadata(&path).map_err(err)?;
    if !m.is_file()
        || m.uid() != crate::user_ids("huou07")?.0
        || m.nlink() != 1
        || m.len() > LIMIT as u64
    {
        return Err(
            "Only one owner-owned UTF-8 export, without aliases, up to 1 MiB can be cleaned".into(),
        );
    }
    if !matches!(
        path.extension().and_then(|s| s.to_str()),
        Some("log" | "jsonl" | "out" | "err" | "txt")
    ) {
        return Err("Select a text log export (.log, .jsonl, .out, .err, .txt)".into());
    }
    closed(&m)?;
    Ok((path, m))
}
fn request(path: &Path, meta: &Metadata, op: &str) -> Value {
    json!({"op":op,"area":"storage","path":path,"length":meta.len(),"expected_dev":meta.dev(),"expected_ino":meta.ino(),"expected_ctime":meta.ctime(),"expected_ctime_nsec":meta.ctime_nsec()})
}
fn actor(v: &Value, bytes: &[u8]) -> Result<Vec<u8>> {
    let mut child = crate::helper::actor(v)?;
    let mut stdin = child.stdin.take().ok_or("File actor input unavailable")?;
    let header = format!("{v}\n");
    let body = bytes.to_vec();
    let writer = std::thread::spawn(move || {
        stdin.write_all(header.as_bytes())?;
        stdin.write_all(&body)
    });
    let mut output = Vec::new();
    child
        .stdout
        .take()
        .ok_or("File actor output unavailable")?
        .take((LIMIT + 8192) as u64)
        .read_to_end(&mut output)
        .map_err(err)?;
    let status = child.wait().map_err(err)?;
    writer
        .join()
        .map_err(|_| "File actor writer failed")?
        .map_err(err)?;
    let split = output
        .iter()
        .position(|b| *b == b'\n')
        .ok_or("Invalid file actor response")?;
    let header: Value =
        serde_json::from_slice(&output[..split]).map_err(|_| "Invalid file actor response")?;
    if !status.success() || header["ok"] != true {
        return Err("File actor rejected the operation; original/recovery data retained".into());
    }
    Ok(output.split_off(split + 1))
}
fn render(path: &Path, m: &Metadata) -> Result<(Vec<u8>, Vec<u8>, Value)> {
    let original = actor(&request(path, m, "fs_read"), &[])?;
    if original.len() != m.len() as usize
        || identity(&fs::metadata(path).map_err(err)?) != identity(m)
    {
        return Err("Log changed; create a new preview".into());
    }
    let (mut cleaned, counts) = crate::redact::clean(&original)?;
    let suppressed = crate::scan::detect_bytes(cleaned.clone())?;
    if suppressed {
        cleaned.fill(0);
        cleaned = b"[H07P: export suppressed because secret signatures remain after redaction]\n"
            .to_vec();
    }
    let summary = json!({"bytes_before":original.len(),"bytes_after":cleaned.len(),"lines":counts.lines,"redacted_lines":counts.redacted_lines,"oversized_lines":counts.oversized_lines,"fully_suppressed":suppressed,"claim":"known signatures only; unknown secrets may remain"});
    Ok((original, cleaned, summary))
}
fn plan(c: &Connection, v: &Value) -> Result<Value> {
    let (path, m) = target(c, v["path"].as_str().ok_or("Log export path is required")?)?;
    let (_, _, summary) = render(&path, &m)?;
    let id = crate::random_token()?;
    let body = json!({"path":path,"identity":identity(&m),"policy_revision":crate::helper::load()?["revision"],"guard_revision":config(c)?["revision"],"summary":summary});
    c.execute("DELETE FROM guard_plans WHERE expires<=?1", [crate::now()])
        .map_err(err)?;
    let count: u64 = c
        .query_row("SELECT count(*) FROM guard_plans", [], |r| r.get(0))
        .map_err(err)?;
    if count >= 100 {
        return Err("Too many active previews; wait five minutes".into());
    }
    c.execute(
        "INSERT INTO guard_plans VALUES(?1,?2,?3)",
        params![id, body.to_string(), crate::now() + 300],
    )
    .map_err(err)?;
    Ok(
        json!({"plan_id":id,"path":path,"summary":summary,"expires_in":300,"original_retained":true,"result_mode":"0600"}),
    )
}
fn clean(c: &Connection, v: &Value) -> Result<Value> {
    if v["confirmed"] != true {
        return Err("Confirm the reviewed cleanup before applying".into());
    }
    let id = v["plan_id"].as_str().ok_or("Preview is required")?;
    let body: String = c
        .query_row(
            "SELECT body FROM guard_plans WHERE id=?1 AND expires>?2",
            params![id, crate::now()],
            |r| r.get(0),
        )
        .map_err(|_| "Preview expired or already used")?;
    let p: Value = serde_json::from_str(&body).map_err(err)?;
    let (path, m) = target(c, p["path"].as_str().ok_or("Invalid preview")?)?;
    if p["identity"] != identity(&m)
        || p["guard_revision"] != config(c)?["revision"]
        || p["policy_revision"] != crate::helper::load()?["revision"]
    {
        return Err("REVISION_CONFLICT: log or policy changed; preview again".into());
    }
    let (mut original, mut cleaned, summary) = render(&path, &m)?;
    let qid = crate::random_token()?;
    let folder = crate::helper::dir().join("guard-quarantine");
    fs::create_dir_all(&folder).map_err(err)?;
    fs::set_permissions(&folder, fs::Permissions::from_mode(0o700)).map_err(err)?;
    let mut backup = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(folder.join(&qid))
        .map_err(err)?;
    backup.write_all(&original).map_err(err)?;
    backup.sync_all().map_err(err)?;
    original.fill(0);
    fs::File::open(&folder)
        .and_then(|f| f.sync_all())
        .map_err(err)?;
    let mut record = json!({"id":qid,"path":path,"at":crate::now(),"bytes":m.len(),"state":"pending","summary":summary});
    c.execute(
        "INSERT INTO guard_quarantine VALUES(?1,?2)",
        params![qid, record.to_string()],
    )
    .map_err(err)?;
    c.execute("DELETE FROM guard_plans WHERE id=?1", [id])
        .map_err(err)?;
    closed(&m)?;
    let mut req = request(&path, &m, "fs_guard_replace");
    req["length"] = json!(cleaned.len());
    let result = actor(&req, &cleaned);
    cleaned.fill(0);
    record["state"] = json!(if result.is_ok() {
        "cleaned"
    } else {
        "failed_original_retained"
    });
    c.execute(
        "UPDATE guard_quarantine SET body=?2 WHERE id=?1",
        params![qid, record.to_string()],
    )
    .map_err(err)?;
    result?;
    event(c, "log_cleaned", path.to_str().unwrap_or("[non-UTF8]"))?;
    Ok(record)
}
fn records(c: &Connection, table: &str) -> Result<Vec<Value>> {
    // Table names come only from fixed call sites.
    let mut q = c
        .prepare(&format!(
            "SELECT body FROM {table} ORDER BY rowid DESC LIMIT 100"
        ))
        .map_err(err)?;
    let values = q.query_map([], |r| r.get::<_, String>(0)).map_err(err)?;
    values
        .map(|v| serde_json::from_str(&v.map_err(err)?).map_err(err))
        .collect()
}
pub(crate) fn control(op: &str, v: &Value) -> Result<Value> {
    let c = crate::helper::db()?;
    match op {
        "guard_status" => {
            let cfg = config(&c)?;
            let policy = crate::helper::load()?;
            Ok(
                json!({"state":if policy["revision"]!=policy["enforced_revision"]{"POLICY_ERROR"}else{"PARTIAL"},"limitation":"UNRESOLVED_SAME_UID: each worker retains its own native harness credential access by owner choice. Detection does not prevent every new secret copy.","config":cfg,"watcher":health().lock().unwrap_or_else(|e|e.into_inner()).clone(),"quarantine":records(&c,"guard_quarantine")?,"source_redaction":"recognized signatures on managed web-worker stdout/stderr; interactive CLI unchanged"}),
            )
        }
        "guard_configure" => {
            let old = config(&c)?;
            if v["revision"] != old["revision"] {
                return Err("REVISION_CONFLICT: reload Guard settings".into());
            }
            let scopes = roots(&v["scopes"], false)?;
            let exports = roots(&v["safe_exports"], true)?;
            let cfg = json!({"revision":old["revision"].as_u64().unwrap_or(0)+1,"enabled":v["enabled"]==true,"content":v["content"]==true,"scopes":scopes,"safe_exports":exports});
            c.execute("INSERT INTO guard_config VALUES(1,?1) ON CONFLICT(id) DO UPDATE SET body=excluded.body",[cfg.to_string()]).map_err(err)?;
            GENERATION.fetch_add(1, Ordering::Relaxed);
            event(&c, "configuration_changed", "")?;
            Ok(cfg)
        }
        "guard_events" => {
            let mut q = c
                .prepare("SELECT id,at,kind,path,ack FROM guard_events ORDER BY id DESC LIMIT 100")
                .map_err(err)?;
            let rows=q.query_map([],|r|Ok(json!({"id":r.get::<_,i64>(0)?,"at":r.get::<_,u64>(1)?,"kind":r.get::<_,String>(2)?,"path":r.get::<_,String>(3)?,"acknowledged":r.get::<_,i64>(4)?!=0}))).map_err(err)?;
            Ok(json!({"events":rows.collect::<std::result::Result<Vec<_>,_>>().map_err(err)?}))
        }
        "guard_ack" => {
            c.execute(
                "UPDATE guard_events SET ack=1 WHERE id=?1",
                [v["id"].as_i64().ok_or("Event ID is required")?],
            )
            .map_err(err)?;
            GENERATION.fetch_add(1, Ordering::Relaxed);
            Ok(json!({"ok":true}))
        }
        "guard_plan" => plan(&c, v),
        "guard_clean" => clean(&c, v),
        "guard_restore" => {
            let id = v["id"].as_str().ok_or("Quarantine ID is required")?;
            if id.len() != 64 || !id.bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err("Invalid quarantine ID".into());
            }
            let _: String = c
                .query_row("SELECT body FROM guard_quarantine WHERE id=?1", [id], |r| {
                    r.get(0)
                })
                .map_err(|_| "Quarantine entry unavailable")?;
            let mut original = fs::read(crate::helper::dir().join("guard-quarantine").join(id))
                .map_err(|_| "Original is unavailable")?;
            if original.len() > LIMIT {
                return Err("Original exceeds recovery budget".into());
            }
            let destination = format!("/recovered-log-{}.txt", crate::random_token()?);
            let r = actor(
                &json!({"op":"fs_upload","area":"nas","path":destination,"length":original.len()}),
                &original,
            );
            original.fill(0);
            r?;
            event(&c, "original_restored_to_private_nas", "")?;
            Ok(json!({"area":"nas","path":destination,"original_retained":true}))
        }
        _ => Err("Unknown Guard operation".into()),
    }
}

/// One bounded inotify instance; no credential content is opened by this watcher.
/// Closed exports are the only automatic content scope, and never auto-mutated.
pub(crate) fn watch_loop() {
    loop {
        if let Err(reason) = watch() {
            if let Ok(c) = crate::helper::db() {
                let _ = event(&c, "watch_gap_rescan_required", "");
            }
            *health().lock().unwrap_or_else(|e| e.into_inner()) =
                json!({"state":"DEGRADED","reason":reason});
            std::thread::sleep(Duration::from_secs(5));
        }
    }
}
fn watch() -> Result<()> {
    let fd = unsafe { libc::inotify_init1(libc::IN_CLOEXEC | libc::IN_NONBLOCK) };
    if fd < 0 {
        return Err("inotify_unavailable".into());
    }
    let mut input = unsafe { fs::File::from_raw_fd(fd) };
    let mut generation = 0;
    let mut watches: HashMap<i32, PathBuf> = HashMap::new();
    let mut cfg = json!({});
    let mut failures;
    let mut overflows = 0u64;
    let mut pending: HashMap<PathBuf, Instant> = HashMap::new();
    let mut buffer = vec![0u8; 65536];
    loop {
        let next = GENERATION.load(Ordering::Relaxed);
        if next != generation {
            for wd in watches.keys() {
                unsafe {
                    libc::inotify_rm_watch(fd, *wd);
                }
            }
            watches.clear();
            pending.clear();
            let c = crate::helper::db()?;
            let gaps:u64=c.query_row("SELECT count(*) FROM guard_events WHERE ack=0 AND kind='watch_gap_rescan_required'",[],|r|r.get(0)).map_err(err)?;
            failures = usize::from(gaps > 0);
            cfg = config(&crate::helper::db()?)?;
            if cfg["enabled"] == true {
                let mut queue: Vec<(PathBuf, usize)> = vec![];
                for p in [
                    "/home/huou07/.ssh",
                    "/home/huou07/.gnupg",
                    "/home/huou07/.secrets",
                    "/home/huou07/.dsh",
                    "/home/huou07/.codex",
                    "/home/huou07/.config/opencode",
                    "/home/huou07/.local/share/opencode",
                ] {
                    // Fixed stores: watch only the root object's permission/lifetime.
                    let name = std::ffi::CString::new(p).map_err(err)?;
                    let wd = unsafe {
                        libc::inotify_add_watch(
                            fd,
                            name.as_ptr(),
                            libc::IN_ATTRIB
                                | libc::IN_MOVE_SELF
                                | libc::IN_DELETE_SELF
                                | libc::IN_ONLYDIR
                                | libc::IN_DONT_FOLLOW,
                        )
                    };
                    if wd < 0 {
                        failures += 1;
                    } else {
                        watches.insert(wd, p.into());
                    }
                }
                for p in cfg["scopes"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                {
                    queue.push((canonical(p)?, 0));
                }
                let mut visited = 0;
                while let Some((path, depth)) = queue.pop() {
                    visited += 1;
                    if visited > 10000 || watches.len() >= 512 {
                        failures += 1;
                        break;
                    }
                    let name =
                        std::ffi::CString::new(path.as_os_str().as_encoded_bytes()).map_err(err)?;
                    let mask = libc::IN_CLOSE_WRITE
                        | libc::IN_MOVED_TO
                        | libc::IN_CREATE
                        | libc::IN_DELETE
                        | libc::IN_ATTRIB
                        | libc::IN_MOVE_SELF
                        | libc::IN_DELETE_SELF
                        | libc::IN_ONLYDIR
                        | libc::IN_DONT_FOLLOW;
                    let wd = unsafe { libc::inotify_add_watch(fd, name.as_ptr(), mask) };
                    if wd < 0 {
                        failures += 1;
                        continue;
                    }
                    watches.insert(wd, path.clone());
                    if depth >= 8 {
                        failures += 1;
                        continue;
                    }
                    for e in fs::read_dir(&path)
                        .map_err(|_| "watch_inventory_unavailable")?
                        .take(10001)
                        .flatten()
                    {
                        visited += 1;
                        if visited > 10000 {
                            failures += 1;
                            break;
                        }
                        if e.file_type().is_ok_and(|t| t.is_dir())
                            && !staging(&e.path())
                            && !crate::scan::excluded_filesystem(&e.path())
                            && !crate::helper::protected(&e.path(), false)
                        {
                            queue.push((e.path(), depth + 1));
                        }
                    }
                }
            }
            generation = next;
            *health().lock().unwrap_or_else(|e| e.into_inner()) = json!({"state":if cfg["enabled"]!=true{"OFF"}else if failures>0{"DEGRADED"}else{"MONITORING"},"watches":watches.len(),"unavailable_or_over_budget":failures,"overflows":overflows,"content":cfg["content"]==true});
        }
        let mut poll = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        if unsafe { libc::poll(&mut poll, 1, 200) } < 0 {
            return Err("watch_poll_failed".into());
        }
        if poll.revents & libc::POLLIN != 0 {
            let n = match input.read(&mut buffer) {
                Ok(n) => n,
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => 0,
                Err(_) => return Err("watch_read_failed".into()),
            };
            let mut offset = 0;
            while offset + std::mem::size_of::<libc::inotify_event>() <= n {
                let ev = unsafe {
                    std::ptr::read_unaligned(
                        buffer.as_ptr().add(offset) as *const libc::inotify_event
                    )
                };
                let size = std::mem::size_of::<libc::inotify_event>();
                let end = offset + size + ev.len as usize;
                if end > n {
                    break;
                }
                if ev.mask & libc::IN_Q_OVERFLOW != 0 {
                    overflows += 1;
                    event(
                        &crate::helper::db()?,
                        "watch_overflow_manual_rescan_required",
                        "",
                    )?;
                    *health().lock().unwrap_or_else(|e| e.into_inner()) = json!({"state":"DEGRADED","reason":"overflow: review scopes and run explicit Auto Detect scan","overflows":overflows});
                    // Do not claim a complete scan or silently clear this condition.
                    return Err("overflow_requires_explicit_scan".into());
                }
                if ev.mask & libc::IN_IGNORED == 0 {
                    if let Some(base) = watches.get(&ev.wd) {
                        let name = &buffer[offset + size..end];
                        let name = &name[..name.iter().position(|b| *b == 0).unwrap_or(name.len())];
                        let path = if name.is_empty() {
                            base.clone()
                        } else {
                            base.join(std::ffi::OsStr::from_bytes(name))
                        };
                        if pending.len() < 512 {
                            pending.insert(path.clone(), Instant::now());
                        } else {
                            return Err("event_queue_budget_requires_rescan".into());
                        }
                        if ev.mask & (libc::IN_CREATE | libc::IN_MOVED_TO) != 0
                            && ev.mask & libc::IN_ISDIR != 0
                            && !staging(&path)
                        {
                            GENERATION.fetch_add(1, Ordering::Relaxed);
                        }
                        if ev.mask & (libc::IN_MOVE_SELF | libc::IN_DELETE_SELF) != 0 {
                            let configured_root = cfg["scopes"].as_array().is_some_and(|roots| {
                                roots
                                    .iter()
                                    .filter_map(Value::as_str)
                                    .any(|root| base == Path::new(root))
                            });
                            if configured_root || crate::helper::protected(base, false) {
                                return Err("watched_root_moved_or_deleted".into());
                            }
                            GENERATION.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                }
                offset = end;
            }
        }
        let ready: Vec<_> = pending
            .iter()
            .filter(|(_, t)| t.elapsed() > Duration::from_millis(150))
            .take(8)
            .map(|(p, _)| p.clone())
            .collect();
        for path in ready {
            pending.remove(&path);
            let c = crate::helper::db()?;
            event(
                &c,
                "filesystem_metadata_changed",
                path.to_str().unwrap_or("[non-UTF8]"),
            )?;
            if cfg["content"] == true {
                if let Ok((p, m)) = target(&c, path.to_str().unwrap_or("")) {
                    match render(&p, &m) {
                        Ok((mut original, mut cleaned, s)) => {
                            original.fill(0);
                            cleaned.fill(0);
                            if s["redacted_lines"].as_u64().unwrap_or(0) > 0
                                || s["fully_suppressed"] == true
                            {
                                event(
                                    &c,
                                    "secret_signature_in_closed_export",
                                    p.to_str().unwrap_or("[non-UTF8]"),
                                )?;
                            }
                        }
                        Err(_) => {
                            event(
                                &c,
                                "export_scan_unavailable",
                                p.to_str().unwrap_or("[non-UTF8]"),
                            )?;
                        }
                    }
                }
            }
        }
    }
}
use std::os::unix::ffi::OsStrExt;
