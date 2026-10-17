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
pub(crate) const CONTROL_OPERATION_TIMEOUT: Duration = Duration::from_secs(900);

const ACL_PATH_BATCH_MAX_COUNT: usize = 4096;
const ACL_PATH_BATCH_MAX_BYTES: usize = 512 * 1024;

fn should_flush_acl_batch(count: usize, argument_bytes: usize) -> bool {
    count >= ACL_PATH_BATCH_MAX_COUNT || argument_bytes >= ACL_PATH_BATCH_MAX_BYTES
}

fn path_argument_bytes(path: &Path) -> usize {
    path.as_os_str().as_encoded_bytes().len().saturating_add(1)
}

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
    c.execute_batch("CREATE TABLE IF NOT EXISTS history(revision INTEGER PRIMARY KEY,body TEXT NOT NULL);CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER,event TEXT);CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,worker TEXT,path TEXT,operation TEXT,revision INTEGER,expires INTEGER,state TEXT,dev INTEGER,ino INTEGER);CREATE TABLE IF NOT EXISTS policy_reviews(id TEXT PRIMARY KEY,digest TEXT NOT NULL,expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);").map_err(err)?;
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
pub(crate) fn worker_setting(policy: &Value, worker: &str) -> Value {
    let specific = &policy["worker_settings"][worker];
    json!({"preset":specific.get("preset").unwrap_or(&policy["preset"]),"workspace":specific.get("workspace").unwrap_or(&policy["workspace"]),"enabled":specific["enabled"].as_bool().unwrap_or(true)})
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
fn immutable_roots() -> &'static [PathBuf] {
    static ROOTS: std::sync::OnceLock<Vec<PathBuf>> = std::sync::OnceLock::new();
    ROOTS
        .get_or_init(|| {
            vec![
                PathBuf::from("/var/lib/h07p-private"),
                dir(),
                std::env::var_os("H07P_NAS_DIR")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| "/var/lib/h07p-private/nas".into()),
                PathBuf::from("/var/lib/huou07-playground"),
                PathBuf::from("/opt/huou07-playground"),
                PathBuf::from("/run/h07p"),
                PathBuf::from("/etc/h07p-workers"),
                PathBuf::from("/usr/lib/huou07-playground"),
                PathBuf::from("/usr/local/libexec/h07p"),
                PathBuf::from("/home/huou07/.config/huou07-playground"),
            ]
        })
        .as_slice()
}
fn private_roots() -> &'static [PathBuf] {
    static ROOTS: std::sync::OnceLock<Vec<PathBuf>> = std::sync::OnceLock::new();
    ROOTS
        .get_or_init(|| {
            let mut roots = Vec::new();
            for base in [Path::new("/home/huou07"), Path::new("/root")] {
                for relative in [
                    ".ssh",
                    ".gnupg",
                    ".aws",
                    ".azure",
                    ".kube",
                    ".docker",
                    ".pki",
                    ".secrets",
                    ".mozilla",
                    ".var",
                    ".claude",
                    ".config/gh",
                    ".config/gcloud",
                    ".config/agent-workbench",
                    ".config/litellm",
                    ".config/omniroute",
                    ".config/keyrings",
                    ".config/chromium",
                    ".config/google-chrome",
                    ".config/BraveSoftware",
                    ".config/containers",
                    ".local/share/keyrings",
                    ".local/share/containers",
                    ".local/share/docker",
                    ".local/share/huou07-playground-migration",
                    ".cache/mozilla",
                    ".cache/chromium",
                    ".cache/google-chrome",
                    ".cache/BraveSoftware",
                    ".cargo/config",
                    ".cargo/config.toml",
                    ".cargo/credentials",
                    ".cargo/credentials.toml",
                ] {
                    roots.push(base.join(relative));
                }
            }
            for relative in [
                ".dsh",
                ".codex",
                ".config/opencode",
                ".local/share/opencode",
                ".local/state/opencode",
                ".cache/opencode",
            ] {
                roots.push(PathBuf::from("/home/huou07").join(relative));
            }
            roots.extend([
                PathBuf::from("/etc/ssh"),
                PathBuf::from("/etc/ssl/private"),
                PathBuf::from("/etc/letsencrypt"),
                PathBuf::from("/etc/sudoers.d"),
            ]);
            roots
        })
        .as_slice()
}
fn readonly_roots() -> &'static [PathBuf] {
    static ROOTS: std::sync::OnceLock<Vec<PathBuf>> = std::sync::OnceLock::new();
    ROOTS
        .get_or_init(|| {
            [
                "/home/huou07/.local/bin",
                "/home/huou07/.local/lib",
                "/home/huou07/.cargo",
                "/home/huou07/.local/share/flutter",
                "/home/huou07/.local/share/playwright-cli",
                "/home/huou07/.local/share/huou07-playground",
                "/home/huou07/.cargo/bin",
                "/home/huou07/.rustup",
                "/home/huou07/.pub-cache/hosted",
                "/home/huou07/.cache/ms-playwright",
                "/home/huou07/.config/systemd",
                "/home/huou07/.config/autostart",
                "/home/huou07/.config/fish",
                "/home/huou07/.config/environment.d",
                "/home/huou07/.config/libvirt",
                "/home/huou07/.bashrc",
                "/home/huou07/.bash_profile",
                "/home/huou07/.bash_logout",
                "/home/huou07/.profile",
                "/home/huou07/.zshrc",
                "/home/huou07/.zprofile",
                "/home/huou07/.gitconfig",
            ]
            .into_iter()
            .map(PathBuf::from)
            .collect()
        })
        .as_slice()
}
fn sensitive_name(name: &str) -> bool {
    let name = name.to_ascii_lowercase();
    [
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        ".bash_history",
        ".zsh_history",
        ".lesshst",
        "auth.json",
        ".credentials.yaml",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "credentials",
        "credentials.toml",
        "known_hosts",
        "passwd",
        "shadow",
        "gshadow",
        "sudoers",
        ".s3cfg",
        ".envrc",
        ".gitcookies",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "authorized_keys",
    ]
    .contains(&name.as_str())
        || [".pem", ".key", ".p12", ".pfx"]
            .iter()
            .any(|suffix| name.ends_with(suffix))
        || ((name == ".env" || name.starts_with(".env.") || name.ends_with(".env"))
            && !["example", "sample", "template"]
                .iter()
                .any(|part| name.contains(part)))
}
pub(crate) fn is_private_path(path: &Path) -> bool {
    let github_hosts = path.file_name().is_some_and(|name| name == "hosts.yml")
        && path
            .parent()
            .is_some_and(|parent| parent.ends_with(".config/gh"));
    github_hosts
        || private_roots().iter().any(|root| within(path, root))
        || path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(sensitive_name)
}
pub(crate) fn immutable(path: &Path, ancestor: bool) -> bool {
    immutable_roots()
        .iter()
        .any(|root| within(path, root) || (ancestor && within(root, path)))
}
pub(crate) fn protected(path: &Path, ancestor: bool) -> bool {
    immutable(path, ancestor)
        || private_roots()
            .iter()
            .any(|root| within(path, root) || (ancestor && within(root, path)))
        || readonly_roots()
            .iter()
            .any(|root| within(path, root) || (ancestor && within(root, path)))
        || path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(sensitive_name)
}
fn walk_scope(
    root: &Path,
    recursive: bool,
    mut visit: impl FnMut(&Path, &fs::Metadata) -> Result<bool>,
) -> Result<usize> {
    use std::{
        os::unix::fs::MetadataExt,
        time::{Duration, Instant},
    };
    const MAX_OBJECTS: usize = 5_000_000;
    const MAX_TIME: Duration = Duration::from_secs(300);

    let metadata = fs::symlink_metadata(root).map_err(err)?;
    if metadata.file_type().is_symlink() || !(metadata.is_dir() || metadata.is_file()) {
        return Err("Select a regular file or directory without a symlink alias".into());
    }
    let device = metadata.dev();
    let started = Instant::now();
    let mut count = 1usize;
    let descend = visit(root, &metadata)?;
    if !recursive || !metadata.is_dir() || !descend {
        return Ok(count);
    }
    let mut stack = vec![(root.to_path_buf(), fs::read_dir(root).map_err(err)?)];
    while let Some((_, entries)) = stack.last_mut() {
        let Some(entry) = entries.next() else {
            stack.pop();
            continue;
        };
        let entry = entry.map_err(err)?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(err)?;
        if metadata.file_type().is_symlink() || metadata.dev() != device {
            continue;
        }
        if !(metadata.is_dir() || metadata.is_file()) {
            continue;
        }
        count += 1;
        if count > MAX_OBJECTS || started.elapsed() > MAX_TIME {
            return Err("Scope exceeds the 5 million object / 5 minute enforcement limit".into());
        }
        let descend = visit(&path, &metadata)?;
        if descend && metadata.is_dir() {
            stack.push((path.clone(), fs::read_dir(path).map_err(err)?));
        }
    }
    Ok(count)
}
fn validate(draft: &Value) -> Result<()> {
    if !["none", "minimal", "balance", "strict"].contains(&draft["preset"].as_str().unwrap_or("")) {
        return Err("Unknown security preset".into());
    }
    let workspace = draft["workspace"].as_str().ok_or("Workspace is required")?;
    let wp = fs::canonicalize(workspace).map_err(err)?;
    if !wp.is_dir() || wp != Path::new(workspace) {
        return Err("Select an existing canonical workspace anywhere on the system".into());
    }
    if let Some(settings) = draft.get("worker_settings") {
        let settings = settings
            .as_object()
            .ok_or("Worker settings must be an object")?;
        for (name, setting) in settings {
            if !workers().contains(&name.as_str()) || !setting.is_object() {
                return Err("Unknown worker configuration".into());
            }
            let merged = worker_setting(draft, name);
            if !["none", "minimal", "balance", "strict"]
                .contains(&merged["preset"].as_str().unwrap_or(""))
            {
                return Err("Unknown worker security level".into());
            }
            if setting.get("enabled").is_some_and(|v| !v.is_boolean()) {
                return Err("Worker enabled must be true or false".into());
            }
            let text = merged["workspace"]
                .as_str()
                .ok_or("Worker workspace is required")?;
            let path = fs::canonicalize(text).map_err(err)?;
            if !path.is_dir() || path != Path::new(text) {
                return Err(
                    "Select a canonical existing worker workspace anywhere on the system".into(),
                );
            }
        }
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
        if !["block", "allow"].contains(&rule["action"].as_str().unwrap_or("")) {
            return Err("Unknown rule action".into());
        }
        if immutable(p, false) {
            return Err(
                "The Playground control plane and private NAS cannot be changed by worker rules"
                    .into(),
            );
        }
        if rule["credential_override"] == true && (rule["action"] != "allow" || !is_private_path(p))
        {
            return Err("A private-path exception must be an Allow rule for one detected or protected target".into());
        }
        if rule["action"] == "allow" && is_private_path(p) && rule["credential_override"] != true {
            return Err("This target is protected by default. Select the exact-file private-path exception and review its warning to allow it.".into());
        }
        if rule["credential_override"] == true {
            use std::os::unix::fs::MetadataExt;
            let metadata = fs::symlink_metadata(p).map_err(err)?;
            if !metadata.is_file() || metadata.nlink() > 1 {
                return Err(
                    "A private-path exception must name one regular, unaliased file".into(),
                );
            }
        }
        if rule["action"] == "block" {
            use std::os::unix::fs::MetadataExt;
            let principals: Vec<_> = affected(rule)
                .into_iter()
                .filter_map(|name| crate::user_ids(name).ok().map(|ids| ids.0))
                .collect();
            for ancestor in p.ancestors().skip(1) {
                if principals.contains(&fs::metadata(ancestor).map_err(err)?.uid()) {
                    return Err("ACL cannot protect a Block through an ancestor owned by that worker. Select an owner-owned boundary; the draft has not been applied.".into());
                }
            }
            walk_scope(p, rule["recursive"] == true, |_, metadata| {
                if principals.contains(&metadata.uid()) {
                    return Err("ACL cannot enforce a Block on an object owned by that worker because its owner can change permissions. Select an owner-owned boundary; no protection has been claimed or applied.".into());
                }
                Ok(true)
            })?;
        }
        if rule["action"] == "allow" {
            use std::os::unix::fs::MetadataExt;
            let metadata = fs::symlink_metadata(p).map_err(err)?;
            if metadata.is_file() && metadata.nlink() > 1 {
                return Err(
                    "Allow cannot target a hard-linked file; choose one unaliased file".into(),
                );
            }
            // Recursive enforcement skips descendant hard links without granting
            // through aliases; dry-run avoids walking a potentially huge tree.
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
        if rule["action"] == "allow"
            && affected(rule).iter().any(|worker| {
                let setting = worker_setting(draft, worker);
                ["strict", "balance"].contains(&setting["preset"].as_str().unwrap_or(""))
                    && !p.starts_with(setting["workspace"].as_str().unwrap_or("/"))
            })
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
            let worker = if u == "h07p-dsh.service" {
                "dsh-worker"
            } else {
                "opencode-worker"
            };
            if worker_setting(&load()?, worker)["enabled"] == false {
                continue;
            }
            let mut c = Command::new("systemctl");
            c.args(["start", u]);
            command(c)?;
        }
    }
    Ok(())
}
fn snapshot(target: &str, recursive: bool) -> Result<PathBuf> {
    use sha2::{Digest, Sha256};
    use std::os::unix::fs::MetadataExt;
    let id = format!("{:x}", Sha256::digest(target.as_bytes()));
    let path = dir().join("acl").join(id);
    if !path.exists() {
        fs::create_dir_all(path.parent().unwrap()).map_err(err)?;
        let temporary = path.with_extension("pending");
        let file = fs::File::create(&temporary).map_err(err)?;
        let mut batch = Vec::with_capacity(ACL_PATH_BATCH_MAX_COUNT);
        let mut batch_bytes = 0usize;
        let result = walk_scope(Path::new(target), recursive, |path, metadata| {
            batch_bytes = batch_bytes.saturating_add(path_argument_bytes(path));
            batch.push((path.to_path_buf(), metadata.dev(), metadata.ino()));
            if should_flush_acl_batch(batch.len(), batch_bytes) {
                snapshot_acl_batch(&file, &mut batch)?;
                batch_bytes = 0;
            }
            Ok(true)
        });
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
            return Err("Could not snapshot original ACL".into());
        }
        if !batch.is_empty() {
            if snapshot_acl_batch(&file, &mut batch).is_err() {
                let _ = fs::remove_file(&temporary);
                return Err("Could not snapshot original ACL".into());
            }
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

fn snapshot_acl_batch(output: &fs::File, batch: &mut Vec<(PathBuf, u64, u64)>) -> Result<()> {
    use std::os::unix::fs::MetadataExt;

    let mut command = Command::new("getfacl");
    command.args(["-p", "--"]);
    for (path, dev, ino) in batch.iter() {
        let current = fs::symlink_metadata(path).map_err(err)?;
        if current.dev() != *dev || current.ino() != *ino {
            return Err("Object changed during ACL snapshot".into());
        }
        command.arg(path);
    }
    let status = command
        .stdout(output.try_clone().map_err(err)?)
        .stderr(Stdio::null())
        .status()
        .map_err(err)?;
    if !status.success() {
        return Err("Could not snapshot original ACL".into());
    }
    batch.clear();
    Ok(())
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
        let output = c
            .env("LC_ALL", "C")
            .arg(format!("--restore={}", p.display()))
            .output()
            .map_err(err)?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            if !restore_failed_only_on_missing_paths(&stderr) {
                return Err("Could not restore original ACL".into());
            }
        }
    }
    Ok(())
}
fn restore_failed_only_on_missing_paths(stderr: &str) -> bool {
    let lines: Vec<_> = stderr
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    !lines.is_empty()
        && lines
            .iter()
            .all(|line| line.ends_with(": No such file or directory"))
}
fn review_digest(v: &Value) -> Result<String> {
    use sha2::{Digest, Sha256};
    let mut request = v.clone();
    if let Some(object) = request.as_object_mut() {
        object.remove("op");
        object.remove("review_id");
    }
    Ok(format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&request).map_err(err)?)
    ))
}
fn private_exception_ancestors(target: &Path) -> Vec<PathBuf> {
    let mut ancestors: Vec<_> = target.ancestors().skip(1).map(Path::to_path_buf).collect();
    ancestors.reverse();
    ancestors
}
fn impact_warnings(v: &Value) -> Vec<String> {
    let mut warnings = Vec::new();
    let workspace = v["workspace"].as_str().unwrap_or("");
    if workspace == "/" || workspace == "/home" {
        warnings.push("The workspace is a broad system directory; worker access still follows existing OS permissions and explicit rules.".into());
    }
    for rule in v["rules"].as_array().into_iter().flatten() {
        let target = rule["target"].as_str().unwrap_or("");
        let path = Path::new(target);
        let broad = ["/", "/home", "/home/huou07"].contains(&target);
        if rule["action"] == "allow" && broad {
            warnings.push(format!("Recursive Allow for {target} can expose ordinary files to the selected workers. Known private stores and detected sensitive files remain blocked."));
        }
        if rule["credential_override"] == true {
            warnings.push(format!("This explicitly allows a private or credential path: {target}. The selected worker can read this target until the rule is removed or expires."));
        }
        if rule["action"] == "block" && broad {
            warnings.push(format!(
                "Recursive Block for {target} can stop workers from using many existing files."
            ));
        }
        if rule["action"] == "allow"
            && rule["operations"].as_array().is_some_and(|ops| {
                ["write", "create", "delete"]
                    .iter()
                    .any(|operation| ops.iter().any(|op| op == operation))
            })
            && readonly_roots().iter().any(|root| within(path, root))
        {
            warnings.push(format!("Allowing writes to shared runtime/tool path {target} can modify tools used by multiple workers."));
        }
        if rule["recursive"] == true
            && rule["action"] == "allow"
            && Path::new(target).components().count() <= 3
        {
            warnings.push(format!(
                "Recursive Allow for {target} covers a large part of the filesystem."
            ));
        }
    }
    warnings.sort();
    warnings.dedup();
    warnings
}
fn acl_spec(
    workers: &[&str],
    rule: &Value,
    action: &str,
    directories: bool,
    recursive: bool,
) -> Result<String> {
    let operations = rule["operations"].as_array().ok_or("Missing operations")?;
    let mut entries = Vec::new();
    let access = if action == "block" {
        "---".to_owned()
    } else {
        format!(
            "{}{}{}",
            if operations.iter().any(|op| op == "read" || op == "list") {
                'r'
            } else {
                '-'
            },
            if operations.iter().any(|op| op == "write") {
                'w'
            } else {
                '-'
            },
            if directories {
                'x'
            } else if operations.iter().any(|op| op == "execute") {
                'X'
            } else {
                '-'
            }
        )
    };
    for worker in workers {
        let (uid, _) = crate::user_ids(worker)?;
        entries.push(format!("u:{uid}:{access}"));
        if directories && recursive {
            entries.push(format!("d:u:{uid}:{access}"));
        }
    }
    if action != "block" {
        let (owner_uid, _) = crate::user_ids("huou07")?;
        entries.push(format!("u:{owner_uid}:{access}"));
        if directories && recursive {
            entries.push(format!("d:u:{owner_uid}:{access}"));
        }
    }
    Ok(entries.join(","))
}
fn set_acl_paths(
    paths: &[PathBuf],
    workers: &[&str],
    rule: &Value,
    action: &str,
    directories: bool,
    recursive: bool,
) -> Result<()> {
    if paths.is_empty() || workers.is_empty() {
        return Ok(());
    }
    let mut cmd = Command::new("setfacl");
    cmd.args([
        "-m",
        &acl_spec(workers, rule, action, directories, recursive)?,
        "--",
    ]);
    cmd.args(paths);
    command(cmd)
}
fn current_workers<'a>(names: &[&'a str]) -> Vec<&'a str> {
    names
        .iter()
        .copied()
        .filter(|name| crate::user_ids(name).is_ok())
        .collect()
}
fn private_workers(path: &Path) -> Vec<&'static str> {
    let native = [
        ("/home/huou07/.dsh", "dsh-worker"),
        ("/home/huou07/.codex", "codex-worker"),
        ("/home/huou07/.config/opencode", "opencode-worker"),
        ("/home/huou07/.local/share/opencode", "opencode-worker"),
        ("/home/huou07/.local/state/opencode", "opencode-worker"),
        ("/home/huou07/.cache/opencode", "opencode-worker"),
    ];
    let owner = native
        .iter()
        .find_map(|(root, worker)| within(path, Path::new(root)).then_some(*worker));
    workers()
        .into_iter()
        .filter(|worker| Some(*worker) != owner)
        .collect()
}
fn deny_rule() -> Value {
    json!({"operations":["list","read","write","create","delete","execute"]})
}
fn apply_scope(
    target: &Path,
    recursive: bool,
    workers: &[&str],
    rule: &Value,
    action: &str,
    privacy: bool,
) -> Result<()> {
    use std::os::unix::fs::MetadataExt;
    let mut directories = Vec::with_capacity(ACL_PATH_BATCH_MAX_COUNT);
    let mut files = Vec::with_capacity(ACL_PATH_BATCH_MAX_COUNT);
    let mut directory_bytes = 0usize;
    let mut file_bytes = 0usize;
    let flush = |paths: &mut Vec<PathBuf>, is_directory: bool| -> Result<()> {
        set_acl_paths(paths, workers, rule, action, is_directory, recursive)?;
        paths.clear();
        Ok(())
    };
    walk_scope(target, recursive, |path, metadata| {
        if privacy && action == "allow" {
            let is_immutable = immutable(path, false);
            let is_private = is_private_path(path);
            let hard_link = metadata.is_file() && metadata.nlink() > 1;
            let is_shared_runtime =
                path != target && readonly_roots().iter().any(|root| within(path, root));
            if is_shared_runtime {
                let readonly = json!({"operations":["list","read","execute"]});
                apply_scope(path, metadata.is_dir(), workers, &readonly, "allow", true)?;
                return Ok(false);
            }
            if is_immutable || is_private || hard_link {
                let denied = if is_private {
                    private_workers(path)
                } else {
                    current_workers(&crate::helper::workers())
                };
                if !denied.is_empty() {
                    apply_scope(
                        path,
                        metadata.is_dir(),
                        &denied,
                        &deny_rule(),
                        "block",
                        false,
                    )?;
                }
                return Ok(false);
            }
        }
        let (batch, argument_bytes, is_directory) = if metadata.is_dir() {
            (&mut directories, &mut directory_bytes, true)
        } else {
            (&mut files, &mut file_bytes, false)
        };
        *argument_bytes = argument_bytes.saturating_add(path_argument_bytes(path));
        batch.push(path.to_path_buf());
        if should_flush_acl_batch(batch.len(), *argument_bytes) {
            flush(batch, is_directory)?;
            *argument_bytes = 0;
        }
        Ok(true)
    })?;
    flush(&mut directories, true)?;
    flush(&mut files, false)?;
    Ok(())
}
fn enforce(policy: &Value) -> Result<()> {
    let rules = policy["rules"].as_array().ok_or("Invalid stored rules")?;
    let active = |rule: &&Value| {
        !rule["expires_at"]
            .as_u64()
            .is_some_and(|t| t <= crate::now())
    };
    // Grants skip known credential/private targets; default and explicit blocks
    // are then applied after every grant, so a parent Allow cannot reopen them.
    for rule in rules
        .iter()
        .filter(|r| r["action"] == "allow")
        .filter(active)
    {
        let names: Vec<_> = affected(rule).into_iter().collect();
        let present = current_workers(&names);
        if present.is_empty() {
            continue;
        }
        let p = Path::new(rule["target"].as_str().ok_or("Missing target")?);
        snapshot(rule["target"].as_str().unwrap(), rule["recursive"] == true)?;
        apply_scope(p, rule["recursive"] == true, &present, rule, "allow", true)?;
    }
    // Shared runtimes stay read/execute-only under broad Allows, but an owner
    // can grant a reviewed, explicit writable subpath such as Flutter's cache.
    for rule in rules
        .iter()
        .filter(|r| r["action"] == "allow")
        .filter(active)
        .filter(|r| {
            r["operations"].as_array().is_some_and(|ops| {
                ["write", "create", "delete"]
                    .iter()
                    .any(|operation| ops.iter().any(|op| op == operation))
            })
        })
        .filter(|r| {
            let path = Path::new(r["target"].as_str().unwrap_or("/"));
            readonly_roots().iter().any(|root| within(path, root))
        })
    {
        let names: Vec<_> = affected(rule).into_iter().collect();
        let present = current_workers(&names);
        if present.is_empty() {
            continue;
        }
        apply_scope(
            Path::new(rule["target"].as_str().ok_or("Missing target")?),
            rule["recursive"] == true,
            &present,
            rule,
            "allow",
            false,
        )?;
    }
    // Restore the managed harness store boundary after broad parent grants.
    for root in private_roots() {
        if !root.exists() {
            continue;
        }
        let denied = private_workers(&root);
        if denied.is_empty() {
            continue;
        }
        let rule = deny_rule();
        apply_scope(&root, true, &denied, &rule, "block", false)?;
    }
    // An explicit sensitive-path exception is applied after defaults, but never
    // after an owner Block rule. Ancestor search rights expose no directory listing.
    for rule in rules
        .iter()
        .filter(|r| r["action"] == "allow" && r["credential_override"] == true)
        .filter(active)
    {
        let names: Vec<_> = affected(rule).into_iter().collect();
        let present = current_workers(&names);
        if present.is_empty() {
            continue;
        }
        let target = Path::new(rule["target"].as_str().ok_or("Missing target")?);
        for ancestor in private_exception_ancestors(target) {
            let search = json!({"operations":["execute"]});
            set_acl_paths(&[ancestor], &present, &search, "allow", false, false)?;
        }
        apply_scope(
            target,
            rule["recursive"] == true,
            &present,
            rule,
            "allow",
            false,
        )?;
    }
    for rule in rules
        .iter()
        .filter(|r| r["action"] == "block")
        .filter(active)
    {
        let names: Vec<_> = affected(rule).into_iter().collect();
        let present = current_workers(&names);
        if present.is_empty() {
            continue;
        }
        let target = rule["target"].as_str().ok_or("Missing target")?;
        snapshot(target, rule["recursive"] == true)?;
        apply_scope(
            Path::new(target),
            rule["recursive"] == true,
            &present,
            rule,
            "block",
            false,
        )?;
        // A worker must not rename a private target out from under its block.
        let mut parent = Path::new(target).parent();
        while let Some(path) = parent {
            if path == Path::new("/") {
                break;
            }
            if path.starts_with("/home/huou07") {
                if let Ok(metadata) = fs::metadata(path) {
                    use std::os::unix::fs::{MetadataExt, PermissionsExt};
                    if metadata.uid() == crate::user_ids("huou07")?.0 {
                        fs::set_permissions(
                            path,
                            fs::Permissions::from_mode(metadata.permissions().mode() | 0o1000),
                        )
                        .map_err(err)?;
                    }
                }
                if path == Path::new("/home/huou07") {
                    break;
                }
            }
            parent = path.parent();
        }
    }
    Ok(())
}

#[cfg(test)]
mod policy_tests {
    use super::{
        private_exception_ancestors, should_flush_acl_batch, ACL_PATH_BATCH_MAX_BYTES,
        ACL_PATH_BATCH_MAX_COUNT,
    };
    use std::path::Path;

    #[test]
    fn exact_private_exception_gets_search_rights_on_every_parent() {
        let ancestors = private_exception_ancestors(Path::new("/home/huou07/.config/gh/hosts.yml"));
        assert_eq!(ancestors.first().unwrap(), Path::new("/"));
        assert!(ancestors.contains(&Path::new("/home/huou07/.config").to_path_buf()));
        assert!(ancestors.contains(&Path::new("/home/huou07/.config/gh").to_path_buf()));
        assert_eq!(
            ancestors.last().unwrap(),
            Path::new("/home/huou07/.config/gh")
        );
    }

    #[test]
    fn acl_command_batches_are_bounded_by_count_and_argument_bytes() {
        assert!(!should_flush_acl_batch(ACL_PATH_BATCH_MAX_COUNT - 1, 1));
        assert!(should_flush_acl_batch(ACL_PATH_BATCH_MAX_COUNT, 1));
        assert!(!should_flush_acl_batch(1, ACL_PATH_BATCH_MAX_BYTES - 1));
        assert!(should_flush_acl_batch(1, ACL_PATH_BATCH_MAX_BYTES));
    }

    #[test]
    fn allow_acls_share_with_primary_owner_and_blocks_do_not_change_owner_acl() {
        let rule =
            serde_json::json!({"operations":["list","read","write","create","delete","execute"]});
        let owner_uid = crate::user_ids("huou07").unwrap().0;
        let worker_uid = crate::user_ids("codex-worker").unwrap().0;
        let allow = super::acl_spec(&["codex-worker"], &rule, "allow", true, true).unwrap();
        assert!(allow.contains(&format!("u:{worker_uid}:rwx")));
        assert!(allow.contains(&format!("d:u:{worker_uid}:rwx")));
        assert!(allow.contains(&format!("u:{owner_uid}:rwx")));
        assert!(allow.contains(&format!("d:u:{owner_uid}:rwx")));

        let block = super::acl_spec(&["codex-worker"], &rule, "block", true, true).unwrap();
        assert!(block.contains(&format!("u:{worker_uid}:---")));
        assert!(block.contains(&format!("d:u:{worker_uid}:---")));
        assert!(!block.contains(&format!("u:{owner_uid}:")));
        assert!(!block.contains(&format!("d:u:{owner_uid}:")));
    }

    #[test]
    fn nonrecursive_directory_acl_does_not_change_default_permissions() {
        let rule = serde_json::json!({"operations":["write","create","delete","execute"]});
        let worker_uid = crate::user_ids("codex-worker").unwrap().0;
        let acl = super::acl_spec(&["codex-worker"], &rule, "allow", true, false).unwrap();
        assert!(acl.contains(&format!("u:{worker_uid}:-wx")));
        assert!(!acl.contains("d:u:"));

        let block = super::acl_spec(&["codex-worker"], &rule, "block", true, false).unwrap();
        assert!(block.contains(&format!("u:{worker_uid}:---")));
        assert!(!block.contains("d:u:"));
    }

    #[test]
    fn acl_restore_only_ignores_missing_paths() {
        assert!(super::restore_failed_only_on_missing_paths(
            "setfacl: /home/huou07/removed-file: No such file or directory\n"
        ));
        assert!(!super::restore_failed_only_on_missing_paths(
            "setfacl: /home/huou07/file: Operation not supported\n"
        ));
        assert!(!super::restore_failed_only_on_missing_paths(""));
    }
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
    p["workers"] = json!(workers()
        .iter()
        .map(|name| {
            let mut setting = worker_setting(&p, name);
            setting["name"] = json!(name);
            setting["state"] = json!(match *name {
                "dsh-worker" => unit_state("h07p-dsh.service"),
                "opencode-worker" => unit_state("h07p-opencode.service"),
                _ => "owner CLI via managed launcher".into(),
            });
            setting
        })
        .collect::<Vec<_>>());
    p["capabilities"] = json!({"acl":true,"independent_write_create_delete":false,"worker_owned_block_boundaries":false,"owner_auth":"Linux PAM","nas_private":true,"approval_operations":["list","read","write","create","delete"],"managed_only":true});
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
            let warnings = impact_warnings(v);
            let review_id = crate::random_token()?;
            let c = db()?;
            c.execute(
                "DELETE FROM policy_reviews WHERE expires<=?1 OR used=1",
                [crate::now() as i64],
            )
            .map_err(err)?;
            c.execute(
                "INSERT INTO policy_reviews(id,digest,expires,used) VALUES(?1,?2,?3,0)",
                params![review_id, review_digest(v)?, crate::now() as i64 + 600],
            )
            .map_err(err)?;
            Ok(
                json!({"ok":true,"review_id":review_id,"requires_confirmation":!warnings.is_empty(),"warnings":warnings,"impact":{"restart_workers":workers(),"rules":v["rules"].as_array().map_or(0,Vec::len),"warning":"Applying terminates managed worker tasks and revokes open handles. Previously read bytes cannot be erased."}}),
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
            if op == "apply" && !impact_warnings(&next).is_empty() {
                let review_id = v["review_id"]
                    .as_str()
                    .ok_or("Review impact and confirm the warning before applying")?;
                let changed = c.execute(
                    "UPDATE policy_reviews SET used=1 WHERE id=?1 AND digest=?2 AND expires>?3 AND used=0",
                    params![review_id, review_digest(v)?, crate::now() as i64],
                ).map_err(err)?;
                if changed != 1 {
                    return Err("Impact review is missing, expired, already used, or no longer matches this draft. Review it again.".into());
                }
            }
            next["revision"] = json!(current["revision"].as_u64().unwrap_or(0) + 1);
            next["enforced_revision"] = Value::Null;
            next.as_object_mut().unwrap().remove("expected_revision");
            next.as_object_mut().unwrap().remove("op");
            next.as_object_mut().unwrap().remove("review_id");
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
                    snapshot(rule["target"].as_str().unwrap(), rule["recursive"] == true)?;
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
fn client(stream: UnixStream, broker: bool, lock: &Arc<Mutex<()>>) {
    let _ = stream.set_read_timeout(Some(CONTROL_OPERATION_TIMEOUT));
    let _ = stream.set_write_timeout(Some(CONTROL_OPERATION_TIMEOUT));
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
    if op.starts_with("worker_setup_") {
        reply(
            input.get_mut(),
            crate::worker_setup::control(op, &v, lock.clone()),
        );
        return;
    }
    if op.starts_with("guard_") {
        let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
        reply(input.get_mut(), crate::guard::control(op, &v));
        return;
    }
    if op.starts_with("vpn_apps_") {
        let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
        reply(input.get_mut(), crate::vpn_apps::control(op, &v));
        return;
    }
    if op.starts_with("app_logins_") {
        let _guard = lock.lock().unwrap_or_else(|e| e.into_inner());
        reply(input.get_mut(), crate::app_logins::control(op, &v));
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

pub(crate) fn maintain_workers(v: &Value) -> Result<Value> {
    let mut policy = load()?;
    if v["expected_revision"] != policy["revision"] {
        return Err(
            "REVISION_CONFLICT: policy changed. Refresh worker setup and review again.".into(),
        );
    }
    let action = v["action"].as_str().ok_or("Select an action")?;
    let selected = v["workers"].as_array().ok_or("Select supported workers")?;
    if action == "start-web" {
        if policy["revision"] != policy["enforced_revision"] {
            return Err("Apply or repair the pending policy before starting workers".into());
        }
        let mut units = Vec::new();
        for worker in selected {
            let name = worker.as_str().ok_or("Invalid worker")?;
            if worker_setting(&policy, name)["enabled"] == false {
                return Err("Enable the selected worker in Permissions first".into());
            }
            let unit = match name {
                "dsh-worker" => "h07p-dsh.service",
                "opencode-worker" => "h07p-opencode.service",
                _ => {
                    return Err(
                        "This harness has no managed web service; use its installed CLI".into(),
                    )
                }
            };
            units.push(unit.to_owned());
        }
        start(&units)?;
        return Ok(json!({"started":units}));
    }
    if action == "reset-acl" {
        let selected_names: std::collections::BTreeSet<_> =
            selected.iter().filter_map(Value::as_str).collect();
        let expected: std::collections::BTreeSet<_> = workers().into_iter().collect();
        if selected_names != expected {
            return Err("ACL reset requires all supported worker identities to be selected".into());
        }
        let active = stop()?;
        let revision = policy["revision"]
            .as_u64()
            .ok_or("Invalid policy revision")?
            .checked_add(1)
            .ok_or("Policy revision exhausted")?;
        policy["revision"] = json!(revision);
        policy["enforced_revision"] = Value::Null;
        save(&policy)?;
        let database = db()?;
        database
            .execute(
                "INSERT OR REPLACE INTO history(revision,body) VALUES(?1,?2)",
                params![revision, policy.to_string()],
            )
            .map_err(err)?;
        audit(
            &database,
            "Saved pre-worker ACL baseline reset requested; all managed worker services stopped",
        )?;
        if let Err(error) = crate::worker_setup::driver(
            action,
            selected,
            v["job_id"].as_str().ok_or("Missing worker setup job")?,
        ) {
            audit(
                &database,
                "Pre-worker ACL reset failed; policy remains pending and workers remain stopped",
            )?;
            return Err(error);
        }
        audit(&database,"Pre-worker ACL baseline restored without deleting project data; worker policy awaits Repair")?;
        return Ok(
            json!({"revision":revision,"enforced_revision":null,"acl_reset":true,"workers_stopped":active,"data_retained":true,"next":"Repair selected ACLs to reapply private-store protections before launching workers"}),
        );
    }
    if !["create", "repair", "remove"].contains(&action) {
        return Err("Unsupported worker maintenance".into());
    }
    let revision = policy["revision"]
        .as_u64()
        .ok_or("Invalid policy revision")?
        .checked_add(1)
        .ok_or("Policy revision exhausted")?;
    if !policy["worker_settings"].is_object() {
        policy["worker_settings"] = json!({});
    }
    for worker in selected {
        let name = worker.as_str().ok_or("Invalid worker")?;
        if !policy["worker_settings"][name].is_object() {
            policy["worker_settings"][name] = json!({});
        }
        if action == "remove" {
            policy["worker_settings"][name]["enabled"] = json!(false);
        }
        if action == "create" && crate::user_ids(name).is_err() {
            policy["worker_settings"][name]["enabled"] = json!(true);
        }
    }
    validate(&policy)?;
    policy["revision"] = json!(revision);
    policy["enforced_revision"] = json!(0);
    save(&policy)?;
    let active = stop()?;
    let database = db()?;
    database
        .execute(
            "INSERT OR REPLACE INTO history(revision,body) VALUES(?1,?2)",
            params![revision, policy.to_string()],
        )
        .map_err(err)?;
    audit(
        &database,
        &format!("Worker maintenance {action} revision {revision} started"),
    )?;
    crate::worker_setup::driver(
        action,
        selected,
        v["job_id"].as_str().ok_or("Missing worker setup job")?,
    )?;
    // Recompile custom rules after broad shared-home provisioning, before any launch.
    enforce(&policy)?;
    policy["enforced_revision"] = json!(revision);
    save(&policy)?;
    database
        .execute(
            "UPDATE history SET body=?2 WHERE revision=?1",
            params![revision, policy.to_string()],
        )
        .map_err(err)?;
    audit(
        &database,
        &format!("Worker maintenance {action} revision {revision} enforced"),
    )?;
    start(&active)?;
    Ok(json!({"revision":revision,"enforced_revision":revision,"data_retained":true}))
}
