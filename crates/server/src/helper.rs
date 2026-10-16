//! Root-owned, peer-credential checked control plane. No request contains shell text.
use rusqlite::{params, Connection};
use serde_json::{json, Value};
use std::os::fd::AsRawFd;
use std::os::unix::{
    net::{UnixListener, UnixStream},
    process::CommandExt,
};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    time::Duration,
};
type Result<T> = std::result::Result<T, String>;
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
pub(crate) fn dir() -> PathBuf {
    std::env::var_os("H07P_CONTROL_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| "/var/lib/h07p-control".into())
}
pub(crate) fn db() -> Result<Connection> {
    let c = Connection::open(dir().join("policy.db")).map_err(err)?;
    c.busy_timeout(Duration::from_secs(10)).map_err(err)?;
    c.execute_batch("CREATE TABLE IF NOT EXISTS history(revision INTEGER PRIMARY KEY,body TEXT NOT NULL);CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER,event TEXT);CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,worker TEXT,path TEXT,operation TEXT,revision INTEGER,expires INTEGER,state TEXT,dev INTEGER,ino INTEGER);").map_err(err)?;
    crate::broker::migrate(&c)?;
    crate::guard::migrate(&c)?;
    Ok(c)
}
fn initial() -> Value {
    json!({"revision":0,"enforced_revision":0,"preset":"none","workspace":"/home/huou07/Projects","rules":[]})
}
pub(crate) fn load() -> Result<Value> {
    match fs::read(dir().join("policy.json")) {
        Ok(s) => serde_json::from_slice(&s).map_err(err),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(initial()),
        Err(e) => Err(err(e)),
    }
}
fn save(value: &Value) -> Result<()> {
    let tmp = dir().join(".policy-new");
    fs::write(&tmp, serde_json::to_vec(value).map_err(err)?).map_err(err)?;
    fs::File::open(&tmp)
        .and_then(|f| f.sync_all())
        .map_err(err)?;
    fs::rename(tmp, dir().join("policy.json")).map_err(err)?;
    fs::File::open(dir())
        .and_then(|f| f.sync_all())
        .map_err(err)
}
pub(crate) fn audit(c: &Connection, event: &str) -> Result<()> {
    c.execute(
        "INSERT INTO audit(at,event) VALUES(?1,?2)",
        params![crate::now() as i64, event],
    )
    .map_err(err)?;
    c.execute(
        "DELETE FROM audit WHERE id < (SELECT max(id)-10000 FROM audit)",
        [],
    )
    .map_err(err)?;
    Ok(())
}
pub(crate) fn workers() -> [&'static str; 3] {
    ["dsh-worker", "codex-worker", "opencode-worker"]
}
fn affected(rule: &Value) -> Vec<&'static str> {
    workers()
        .into_iter()
        .filter(|u| {
            rule["worker"].as_str().unwrap_or("*") == "*" || rule["worker"].as_str() == Some(u)
        })
        .collect()
}
fn within(path: &Path, base: &Path) -> bool {
    path == base || path.starts_with(base)
}
pub(crate) fn protected(path: &Path, ancestor: bool) -> bool {
    let mut roots = vec![
        PathBuf::from("/etc"),
        PathBuf::from("/usr"),
        PathBuf::from("/root"),
        PathBuf::from("/var/lib/h07p-private"),
        dir(),
        std::env::var_os("H07P_NAS_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| "/var/lib/h07p-private/nas".into()),
        PathBuf::from("/var/lib/huou07-playground"),
        PathBuf::from("/opt/huou07-playground"),
        PathBuf::from("/run/h07p"),
    ];
    for p in [
        ".ssh",
        ".gnupg",
        ".secrets",
        ".dsh",
        ".codex",
        ".config/opencode",
        ".local/share/opencode",
        ".local/state/opencode",
        ".cache/opencode",
        ".local/bin",
        ".local/lib",
        ".config/systemd",
        ".config/huou07-playground",
        ".config/litellm",
        ".config/omniroute",
        ".config/agent-workbench",
        ".config/gh",
        ".local/share/containers",
        ".local/share/docker",
    ] {
        roots.push(PathBuf::from("/home/huou07").join(p));
    }
    roots
        .iter()
        .any(|r| within(path, r) || (ancestor && within(r, path)))
}
fn validate(draft: &Value) -> Result<()> {
    if !["none", "minimal", "balance", "strict"].contains(&draft["preset"].as_str().unwrap_or("")) {
        return Err("Unknown security preset".into());
    }
    let workspace = draft["workspace"].as_str().ok_or("Workspace is required")?;
    let wp = fs::canonicalize(workspace).map_err(err)?;
    if !wp.is_dir() || !wp.starts_with("/home/huou07/Projects") {
        return Err("Select an existing workspace below /home/huou07/Projects".into());
    }
    let rules = draft["rules"].as_array().ok_or("Rules must be an array")?;
    if rules.len() > 200 {
        return Err("At most 200 rules per revision".into());
    }
    for rule in rules {
        if affected(rule).is_empty() {
            return Err("Unknown worker".into());
        }
        let text = rule["target"].as_str().ok_or("Target is required")?;
        let p = Path::new(text);
        if !p.is_absolute()
            || text.chars().any(char::is_control)
            || p.components()
                .any(|c| matches!(c, std::path::Component::ParentDir))
        {
            return Err("Use an absolute path without traversal".into());
        }
        let canonical = fs::canonicalize(p).map_err(err)?;
        if canonical != p {
            return Err("Select the canonical target, not a symlink or alias path".into());
        }
        let immutable_nas_block = p.starts_with(
            std::env::var("H07P_NAS_DIR").unwrap_or_else(|_| "/var/lib/h07p-private/nas".into()),
        ) && rule["action"] == "block";
        if protected(p, true) && !immutable_nas_block {
            return Err("Administration, credentials, runtime and NAS boundaries cannot be changed by worker rules".into());
        }
        if !["block", "allow"].contains(&rule["action"].as_str().unwrap_or("")) {
            return Err("Unknown rule action".into());
        }
        // A root helper must never turn owner policy into a privilege grant on
        // root-owned files or another account's objects, including hardlink aliases.
        if rule["action"] == "allow" {
            use std::os::unix::fs::MetadataExt;
            let owner = crate::user_ids("huou07")?.0;
            let mut pending = vec![p.to_path_buf()];
            let mut count = 0;
            while let Some(path) = pending.pop() {
                count += 1;
                if count > 10000 {
                    return Err("Allow scope exceeds 10000 objects; select a smaller scope".into());
                }
                let m = fs::symlink_metadata(&path).map_err(err)?;
                if m.uid() != owner
                    || m.file_type().is_symlink()
                    || (m.is_file() && m.nlink() != 1)
                    || protected(&path, false)
                {
                    return Err("Allow requires ordinary owner-owned objects without hardlink or symlink aliases".into());
                }
                if m.is_dir() && rule["recursive"] == true {
                    for child in fs::read_dir(&path).map_err(err)? {
                        pending.push(child.map_err(err)?.path());
                    }
                }
            }
        }
        let ops = rule["operations"]
            .as_array()
            .ok_or("Select concrete operations")?;
        if ops.is_empty()
            || ops.iter().any(|o| {
                !["list", "read", "write", "create", "delete", "execute"]
                    .contains(&o.as_str().unwrap_or(""))
            })
        {
            return Err("Invalid operation list".into());
        }
        let writes = ["write", "create", "delete"].map(|s| ops.iter().any(|o| o == s));
        if writes.iter().any(|x| *x) && !writes.iter().all(|x| *x) {
            return Err("ACL cannot isolate write/create/delete independently; select all three or none. No permissions were changed.".into());
        }
        if rule["action"] == "block" && ops.len() != 6 {
            return Err("Direct ACL Block protects the complete object; select all six operations. Fine-grained negative ACLs are unsupported.".into());
        }
        if ["strict", "balance"].contains(&draft["preset"].as_str().unwrap_or(""))
            && rule["action"] == "allow"
            && !p.starts_with(&wp)
        {
            return Err("Strict/balance outside-workspace direct Allow is unsupported; use a scoped broker approval".into());
        }
        if let Some(t) = rule["expires_at"].as_u64() {
            if t <= crate::now() {
                return Err("Rule expiry is in the past".into());
            }
        }
    }
    Ok(())
}
fn command(mut command: Command) -> Result<()> {
    let status = command
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(err)?;
    if status.success() {
        Ok(())
    } else {
        Err("OS enforcement command failed; affected workers remain stopped".into())
    }
}
fn unit_state(name: &str) -> String {
    Command::new("systemctl")
        .args(["is-active", name])
        .output()
        .ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|| "unavailable".into())
}
fn managed_units() -> Vec<String> {
    let mut result = vec!["h07p-dsh.service".into(), "h07p-opencode.service".into()];
    if let Ok(units) = std::env::var("H07P_MANAGED_UNITS") {
        return units
            .split_whitespace()
            .filter(|u| {
                u.starts_with("h07p-test-")
                    && u.ends_with(".service")
                    && u.chars()
                        .all(|c| c.is_ascii_alphanumeric() || ".-_".contains(c))
            })
            .map(str::to_owned)
            .collect();
    }
    if let Ok(o) = Command::new("systemctl")
        .args([
            "list-units",
            "--all",
            "--plain",
            "--no-legend",
            "h07p-worker-*",
        ])
        .output()
    {
        for line in String::from_utf8_lossy(&o.stdout).lines() {
            if let Some(s) = line.split_whitespace().next() {
                if s.starts_with("h07p-worker-") {
                    result.push(s.into());
                }
            }
        }
    }
    result
}
fn stop() -> Result<Vec<String>> {
    let active: Vec<_> = managed_units()
        .into_iter()
        .filter(|s| unit_state(s) == "active")
        .collect();
    for u in &active {
        let mut c = Command::new("systemctl");
        c.args(["stop", u]);
        command(c)?;
    }
    Ok(active)
}
fn start(units: &[String]) -> Result<()> {
    for u in units {
        if u == "h07p-dsh.service" || u == "h07p-opencode.service" {
            let mut c = Command::new("systemctl");
            c.args(["start", u]);
            command(c)?;
        }
    }
    Ok(())
}
fn snapshot(target: &str) -> Result<PathBuf> {
    use sha2::{Digest, Sha256};
    let id = format!("{:x}", Sha256::digest(target.as_bytes()));
    let path = dir().join("acl").join(id);
    if !path.exists() {
        fs::create_dir_all(path.parent().unwrap()).map_err(err)?;
        let temporary = path.with_extension("pending");
        let file = fs::File::create(&temporary).map_err(err)?;
        let status = Command::new("getfacl")
            .args(["-R", "-P", "-p", "--", target])
            .stdout(file)
            .stderr(Stdio::null())
            .status()
            .map_err(err)?;
        if !status.success() {
            let _ = fs::remove_file(&temporary);
            return Err("Could not snapshot original ACL".into());
        }
        fs::File::open(&temporary)
            .and_then(|f| f.sync_all())
            .map_err(err)?;
        fs::rename(&temporary, &path).map_err(err)?;
        fs::File::open(path.parent().unwrap())
            .and_then(|f| f.sync_all())
            .map_err(err)?;
    }
    Ok(path)
}
fn restore() -> Result<()> {
    let root = dir().join("acl");
    if !root.exists() {
        return Ok(());
    }
    for e in fs::read_dir(root).map_err(err)? {
        let p = e.map_err(err)?.path();
        if !p
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.len() == 64 && n.bytes().all(|b| b.is_ascii_hexdigit()))
        {
            continue;
        }
        let mut c = Command::new("setfacl");
        c.arg(format!("--restore={}", p.display()));
        command(c)?;
    }
    Ok(())
}
fn enforce(policy: &Value) -> Result<()> {
    let rules = policy["rules"].as_array().ok_or("Invalid stored rules")?;
    // All grants first, all blocks last. Parent grants cannot silently undo a block.
    for action in ["allow", "block"] {
        for rule in rules.iter().filter(|r| r["action"] == action) {
            if rule["expires_at"]
                .as_u64()
                .is_some_and(|t| t <= crate::now())
            {
                continue;
            }
            let p = rule["target"].as_str().ok_or("Missing target")?;
            let _ = snapshot(p)?;
            let ops = rule["operations"].as_array().ok_or("Missing operations")?;
            let permission = if action == "block" {
                "---".to_owned()
            } else {
                format!(
                    "{}{}{}",
                    if ops.iter().any(|o| o == "read" || o == "list") {
                        'r'
                    } else {
                        '-'
                    },
                    if ops.iter().any(|o| o == "write") {
                        'w'
                    } else {
                        '-'
                    },
                    if Path::new(p).is_dir() || ops.iter().any(|o| o == "execute") {
                        'x'
                    } else {
                        '-'
                    }
                )
            };
            let spec = affected(rule)
                .iter()
                .map(|u| format!("u:{u}:{permission}"))
                .collect::<Vec<_>>()
                .join(",");
            let mut cmd = Command::new("setfacl");
            if rule["recursive"].as_bool().unwrap_or(false) {
                cmd.args(["-R", "-P"]);
            }
            cmd.args(["-m", &spec, "--", p]);
            command(cmd)?;
            // No new child can bypass a directory Block. Default ACLs cover recreated children.
            if Path::new(p).is_dir() {
                let default = affected(rule)
                    .iter()
                    .map(|u| format!("d:u:{u}:{permission}"))
                    .collect::<Vec<_>>()
                    .join(",");
                let mut cmd = Command::new("setfacl");
                cmd.args(["-m", &default, "--", p]);
                command(cmd)?;
            }
            if action == "block" {
                let mut parent = Path::new(p).parent();
                while let Some(q) = parent {
                    if q == Path::new("/") {
                        break;
                    }
                    if let Ok(m) = fs::metadata(q) {
                        use std::os::unix::fs::PermissionsExt;
                        fs::set_permissions(
                            q,
                            fs::Permissions::from_mode(m.permissions().mode() | 0o1000),
                        )
                        .map_err(err)?;
                    }
                    if q == Path::new("/home/huou07") || q == Path::new("/tmp") {
                        break;
                    }
                    parent = q.parent();
                }
            }
        }
    }
    Ok(())
}
fn status() -> Result<Value> {
    let mut p = load()?;
    let c = db()?;
    let mut q=c.prepare("SELECT id,worker,path,operation,revision,expires,state FROM approvals ORDER BY expires DESC LIMIT 100").map_err(err)?;
    let rows=q.query_map([],|r|Ok(json!({"id":r.get::<_,String>(0)?,"worker":r.get::<_,String>(1)?,"target":r.get::<_,String>(2)?,"operation":r.get::<_,String>(3)?,"revision":r.get::<_,i64>(4)?,"expires_at":r.get::<_,i64>(5)?,"state":r.get::<_,String>(6)?}))).map_err(err)?;
    p["approvals"] = Value::Array(
        rows.filter_map(|r| r.ok())
            .map(|mut r| {
                if r["expires_at"].as_u64().unwrap_or(0) <= crate::now() {
                    r["state"] = "expired".into();
                }
                r
            })
            .collect(),
    );
    let mut q = c
        .prepare("SELECT at,event FROM audit ORDER BY id DESC LIMIT 100")
        .map_err(err)?;
    p["audit"] = Value::Array(
        q.query_map([], |r| {
            Ok(json!({"at":r.get::<_,i64>(0)?,"event":r.get::<_,String>(1)?}))
        })
        .map_err(err)?
        .filter_map(|r| r.ok())
        .collect(),
    );
    p["workers"] = json!([{"name":"dsh-worker","state":unit_state("h07p-dsh.service"),"preset":p["preset"]},{"name":"codex-worker","state":"owner CLI via managed launcher","preset":p["preset"]},{"name":"opencode-worker","state":unit_state("h07p-opencode.service"),"preset":p["preset"]}]);
    p["capabilities"] = json!({"acl":true,"independent_write_create_delete":false,"owner_auth":"Linux PAM","nas_private":true,"approval_operations":["list","read","write","create","delete"],"managed_only":true});
    Ok(p)
}
fn control(op: &str, v: &Value) -> Result<Value> {
    match op {
        "status" => status(),
        "dry-run" => {
            validate(v)?;
            let p = load()?;
            if v["expected_revision"].as_u64() != p["revision"].as_u64() {
                return Err("REVISION_CONFLICT: reload the current policy before applying".into());
            }
            Ok(
                json!({"ok":true,"impact":{"restart_workers":workers(),"rules":v["rules"].as_array().map_or(0,Vec::len),"warning":"Applying terminates managed worker tasks and revokes open handles. Previously read bytes cannot be erased."}}),
            )
        }
        "apply" | "rollback" => {
            let current = load()?;
            if v["expected_revision"].as_u64() != current["revision"].as_u64() {
                return Err("REVISION_CONFLICT: reload the current policy".into());
            }
            let c = db()?;
            let mut next = if op == "rollback" {
                let text: String = c
                    .query_row(
                        "SELECT body FROM history WHERE revision=?1",
                        [v["revision"].as_u64().ok_or("Missing rollback revision")?],
                        |r| r.get(0),
                    )
                    .map_err(err)?;
                serde_json::from_str(&text).map_err(err)?
            } else {
                v.clone()
            };
            validate(&next)?;
            next["revision"] = json!(current["revision"].as_u64().unwrap_or(0) + 1);
            next["enforced_revision"] = Value::Null;
            next.as_object_mut().unwrap().remove("expected_revision");
            c.execute(
                "INSERT OR IGNORE INTO history(revision,body) VALUES(?1,?2)",
                params![
                    current["revision"].as_u64().unwrap_or(0),
                    current.to_string()
                ],
            )
            .map_err(err)?;
            // Publish the pending state before touching the OS. A crash or failed
            // rollback must never leave a stale "Enforced" revision visible.
            save(&next)?;
            let active = match stop() {
                Ok(units) => units,
                Err(error) => {
                    let _ = save(&current);
                    return Err(error);
                }
            };
            if let Err(error) = restore().and_then(|_| {
                for rule in next["rules"].as_array().unwrap() {
                    snapshot(rule["target"].as_str().unwrap())?;
                }
                enforce(&next)
            }) {
                if current["enforced_revision"].as_u64() == current["revision"].as_u64()
                    && restore().and_then(|_| enforce(&current)).is_ok()
                {
                    let _ = save(&current);
                }
                audit(&c, "Policy apply failed; workers stopped")?;
                return Err(error);
            }
            next["enforced_revision"] = next["revision"].clone();
            save(&next)?;
            start(&active)?;
            audit(
                &c,
                "Policy revision enforced; managed worker processes recreated",
            )?;
            status()
        }
        "approve" => {
            let c = db()?;
            let state = if v["allow"] == true {
                "approved"
            } else {
                "denied"
            };
            let changed=c.execute("UPDATE approvals SET state=?1 WHERE id=?2 AND state='pending' AND expires>?3 AND revision=?4",params![state,v["id"].as_str().ok_or("Missing approval id")?,crate::now(),load()?["revision"].as_u64().unwrap_or(0)]).map_err(err)?;
            if changed != 1 {
                return Err("Approval is expired, stale, or already decided".into());
            }
            audit(&c, "Owner decided a scoped worker request")?;
            Ok(json!({"ok":true}))
        }
        _ => Err("Unsupported control operation".into()),
    }
}
#[repr(C)]
struct PamMessage {
    style: libc::c_int,
    msg: *const libc::c_char,
}
#[repr(C)]
struct PamResponse {
    resp: *mut libc::c_char,
    code: libc::c_int,
}
#[repr(C)]
struct PamConv {
    conv: unsafe extern "C" fn(
        libc::c_int,
        *mut *const PamMessage,
        *mut *mut PamResponse,
        *mut libc::c_void,
    ) -> libc::c_int,
    data: *mut libc::c_void,
}
unsafe extern "C" fn converse(
    n: libc::c_int,
    msg: *mut *const PamMessage,
    out: *mut *mut PamResponse,
    data: *mut libc::c_void,
) -> libc::c_int {
    if !(1..=8).contains(&n) {
        return 19;
    }
    let array = libc::calloc(n as usize, std::mem::size_of::<PamResponse>()) as *mut PamResponse;
    if array.is_null() {
        return 5;
    }
    for i in 0..n as isize {
        let style = (**msg.offset(i)).style;
        if style == 1 || style == 2 {
            (*array.offset(i)).resp = libc::strdup(data as *const libc::c_char);
        } else if style != 3 && style != 4 {
            libc::free(array as *mut _);
            return 19;
        }
    }
    *out = array;
    0
}
fn authenticate(v: &Value) -> Result<Value> {
    let expected = std::env::var("H07P_OWNER").unwrap_or_else(|_| "huou07".into());
    if v["username"].as_str() != Some(&expected) {
        return Err("Invalid owner credentials".into());
    }
    let password = v["password"]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= 1024)
        .ok_or("Invalid owner credentials")?;
    #[cfg(target_os = "linux")]
    unsafe {
        let lib = libc::dlopen(c"libpam.so.0".as_ptr(), libc::RTLD_NOW);
        if lib.is_null() {
            return Err("Linux PAM is unavailable".into());
        }
        type Start = unsafe extern "C" fn(
            *const libc::c_char,
            *const libc::c_char,
            *const PamConv,
            *mut *mut libc::c_void,
        ) -> i32;
        type Auth = unsafe extern "C" fn(*mut libc::c_void, i32) -> i32;
        type End = unsafe extern "C" fn(*mut libc::c_void, i32) -> i32;
        for symbol in [
            c"pam_start",
            c"pam_authenticate",
            c"pam_acct_mgmt",
            c"pam_end",
        ] {
            if libc::dlsym(lib, symbol.as_ptr()).is_null() {
                libc::dlclose(lib);
                return Err("Linux PAM interface unavailable".into());
            }
        }
        let start: Start = std::mem::transmute(libc::dlsym(lib, c"pam_start".as_ptr()));
        let auth: Auth = std::mem::transmute(libc::dlsym(lib, c"pam_authenticate".as_ptr()));
        let account: Auth = std::mem::transmute(libc::dlsym(lib, c"pam_acct_mgmt".as_ptr()));
        let end: End = std::mem::transmute(libc::dlsym(lib, c"pam_end".as_ptr()));
        let pw = std::ffi::CString::new(password).map_err(|_| "Invalid owner credentials")?;
        let user = std::ffi::CString::new(expected).map_err(err)?;
        let conv = PamConv {
            conv: converse,
            data: pw.as_ptr() as *mut _,
        };
        let mut handle = std::ptr::null_mut();
        let mut rc = start(c"login".as_ptr(), user.as_ptr(), &conv, &mut handle);
        if rc == 0 {
            rc = auth(handle, 0);
            if rc == 0 {
                rc = account(handle, 0);
            }
            end(handle, rc);
        }
        libc::dlclose(lib);
        if rc != 0 {
            return Err("Invalid owner credentials".into());
        }
    }
    #[cfg(not(target_os = "linux"))]
    return Err("Owner authentication requires Linux PAM".into());
    Ok(json!({"username":v["username"]}))
}
pub(crate) fn actor(v: &Value) -> Result<std::process::Child> {
    let area = v["area"].as_str().unwrap_or("storage");
    let user = if area == "nas" {
        "huou07-playground"
    } else {
        "huou07"
    };
    let (uid, gid) = crate::user_ids(user)?;
    // Storage inherits the owner's actual Unix group rights; workers still drop
    // all supplementary groups in sandbox.rs. Resolve NSS before fork.
    let account = std::ffi::CString::new(user).map_err(err)?;
    let mut groups = vec![gid; 32];
    let mut count = groups.len() as libc::c_int;
    if unsafe { libc::getgrouplist(account.as_ptr(), gid, groups.as_mut_ptr(), &mut count) } < 0 {
        if !(1..=256).contains(&count) {
            return Err("Owner group inventory exceeds the supported bound".into());
        }
        groups.resize(count as usize, gid);
        if unsafe { libc::getgrouplist(account.as_ptr(), gid, groups.as_mut_ptr(), &mut count) } < 0
        {
            return Err("Owner groups unavailable".into());
        }
    }
    groups.truncate(count as usize);
    let mut c = Command::new(std::env::current_exe().map_err(err)?);
    c.arg("fs-actor")
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env(
            "H07P_NAS_DIR",
            std::env::var("H07P_NAS_DIR").unwrap_or_else(|_| "/var/lib/h07p-private/nas".into()),
        )
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    unsafe {
        c.pre_exec(move || {
            if libc::setgroups(groups.len(), groups.as_ptr()) != 0
                || libc::setgid(gid) != 0
                || libc::setuid(uid) != 0
            {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    c.spawn().map_err(err)
}
fn file_request(v: &Value, input: &mut BufReader<UnixStream>) -> Result<()> {
    let mut child = actor(v)?;
    let mut cin = child.stdin.take().ok_or("File actor stdin unavailable")?;
    writeln!(cin, "{}", v).map_err(err)?;
    if v["op"] == "fs_upload" {
        let length = v["length"]
            .as_u64()
            .filter(|n| *n <= 512 * 1024 * 1024)
            .ok_or("Upload limit exceeded")?;
        let _ = std::io::copy(&mut input.take(length), &mut cin);
    }
    drop(cin);
    let mut output = child.stdout.take().ok_or("File actor stdout unavailable")?;
    std::io::copy(&mut output, input.get_mut()).map_err(err)?;
    let _ = child.wait();
    Ok(())
}
fn peer(stream: &UnixStream) -> Result<u32> {
    let mut cred: libc::ucred = unsafe { std::mem::zeroed() };
    let mut len = std::mem::size_of_val(&cred) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            &mut cred as *mut _ as *mut _,
            &mut len,
        )
    } != 0
    {
        return Err("Cannot verify kernel peer credentials".into());
    }
    Ok(cred.uid)
}
fn reply(stream: &mut UnixStream, result: Result<Value>) {
    let value = match result {
        Ok(v) => json!({"ok":true,"data":v}),
        Err(e) => json!({"ok":false,"error":e}),
    };
    let _ = writeln!(stream, "{}", value);
}
fn client(stream: UnixStream, broker: bool, lock: &Mutex<()>) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(120)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(120)));
    let uid = match peer(&stream) {
        Ok(u) => u,
        Err(_) => return,
    };
    let allowed = crate::user_ids("huou07-playground")
        .map(|u| u.0)
        .unwrap_or(u32::MAX);
    if !broker && uid != 0 && uid != allowed {
        return;
    }
    let mut input = BufReader::new(stream);
    let mut line = String::new();
    if input.by_ref().take(131073).read_line(&mut line).is_err() || line.len() > 131072 {
        return;
    }
    let v: Value = match serde_json::from_str(&line) {
        Ok(v) => v,
        Err(_) => return,
    };
    let op = v["op"].as_str().unwrap_or("");
    if broker {
        let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
        reply(input.get_mut(), broker_request(uid, &v));
        return;
    }
    if op.starts_with("guard_") {
        let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
        reply(input.get_mut(), crate::guard::control(op, &v));
        return;
    }
    if op.starts_with("fs_") {
        if let Err(e) = file_request(&v, &mut input) {
            reply(input.get_mut(), Err(e));
        }
        return;
    }
    if op == "authenticate" {
        reply(input.get_mut(), authenticate(&v));
        return;
    }
    if op == "scan" {
        reply(input.get_mut(), scan(&v));
        return;
    }
    let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
    reply(input.get_mut(), control(op, &v));
}
fn scan(v: &Value) -> Result<Value> {
    crate::scan::run(v)
}
fn broker_request(uid: u32, v: &Value) -> Result<Value> {
    crate::broker::request(uid, v)
}
fn listen(path: &Path, mode: u32) -> Result<UnixListener> {
    use std::os::unix::fs::PermissionsExt;
    if path.exists() {
        fs::remove_file(path).map_err(err)?;
    }
    let l = UnixListener::bind(path).map_err(err)?;
    fs::set_permissions(path, fs::Permissions::from_mode(mode)).map_err(err)?;
    Ok(l)
}
pub fn run() -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    if unsafe { libc::geteuid() } != 0 {
        return Err("Control helper requires root".into());
    }
    fs::create_dir_all(dir()).map_err(err)?;
    fs::set_permissions(dir(), fs::Permissions::from_mode(0o700)).map_err(err)?;
    let _ = db()?;
    let admin = std::env::var_os("H07P_HELPER_SOCKET")
        .map(PathBuf::from)
        .unwrap_or_else(|| "/run/h07p/admin.sock".into());
    fs::create_dir_all(admin.parent().unwrap()).map_err(err)?;
    fs::set_permissions(admin.parent().unwrap(), fs::Permissions::from_mode(0o755)).map_err(err)?;
    let listener = listen(&admin, 0o660)?;
    let (_, gid) = crate::user_ids("huou07-playground")?;
    let name = std::ffi::CString::new(admin.as_os_str().as_encoded_bytes()).map_err(err)?;
    unsafe {
        libc::chown(name.as_ptr(), 0, gid);
    }
    let broker = listen(&admin.with_file_name("broker.sock"), 0o666)?;
    let lock = Arc::new(Mutex::new(()));
    let bl = lock.clone();
    std::thread::spawn(move || {
        for s in broker.incoming().flatten() {
            let l = bl.clone();
            crate::bounded_spawn(move || client(s, true, &l));
        }
    });
    std::thread::spawn(crate::guard::watch_loop);
    if std::env::var("H07P_RELAYS").as_deref() != Ok("false") {
        std::thread::spawn(crate::relays::run);
    }
    let expiry = lock.clone();
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(2));
        let _guard = expiry.lock().unwrap_or_else(|e| e.into_inner());
        if let Ok(mut p) = load() {
            let expired = p["rules"].as_array().is_some_and(|rs| {
                rs.iter()
                    .any(|r| r["expires_at"].as_u64().is_some_and(|t| t <= crate::now()))
            });
            if expired {
                let old = p["rules"].as_array().cloned().unwrap_or_default();
                p["rules"] = json!(old
                    .into_iter()
                    .filter(|r| r["expires_at"].as_u64().is_none_or(|t| t > crate::now()))
                    .collect::<Vec<_>>());
                p["expected_revision"] = p["revision"].clone();
                let _ = control("apply", &p);
            }
        }
    });
    for s in listener.incoming().flatten() {
        let l = lock.clone();
        crate::bounded_spawn(move || client(s, false, &l));
    }
    Ok(())
}
