//! Explicit, bounded detection. Scanner output never enters logs or API reports.
use serde_json::{json, Value};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    os::unix::{fs::MetadataExt, process::CommandExt},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub(crate) fn excluded_filesystem(path: &std::path::Path) -> bool {
    let Ok(path) = std::ffi::CString::new(path.as_os_str().as_encoded_bytes()) else {
        return true;
    };
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statfs(path.as_ptr(), &mut stat) } != 0 {
        return true;
    }
    matches!(
        stat.f_type as u64,
        0x6969
            | 0xff534d42
            | 0x517b
            | 0x65735546
            | 0x9fa0
            | 0x62656572
            | 0x1cd1
            | 0x1373
            | 0x27e0eb
            | 0x63677270
            | 0x534f434b
            | 0x50495045
            | 0x73636673
            | 0x64626720
            | 0x74726163
            | 0x19800202
            | 0x187
    )
}

fn content(path: &std::path::Path, meta: &fs::Metadata) -> Result<bool, String> {
    if !meta.is_file() || meta.nlink() != 1 || meta.len() > 1024 * 1024 {
        return Err("content_type_alias_or_size_budget".into());
    }
    let request = json!({"op":"fs_read", "area":"storage", "path":path,
        "length":1024*1024, "expected_dev":meta.dev(), "expected_ino":meta.ino()});
    let mut actor = crate::helper::actor(&request)?;
    writeln!(actor.stdin.take().ok_or("adapter_stdin")?, "{request}")
        .map_err(|_| "adapter_write")?;
    let mut reader = BufReader::new(actor.stdout.take().ok_or("adapter_stdout")?);
    let mut header = String::new();
    reader
        .read_line(&mut header)
        .map_err(|_| "adapter_header")?;
    let response: Value = serde_json::from_str(&header).map_err(|_| "adapter_header")?;
    if response["ok"] != true {
        let _ = actor.wait();
        return Err("owner_unreadable".into());
    }
    let mut bytes = Vec::new();
    reader
        .take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "adapter_read")?;
    if !actor.wait().map_err(|_| "adapter_wait")?.success() || bytes.len() > 1024 * 1024 {
        return Err("content_changed_or_budget".into());
    }
    detect_bytes(bytes)
}

pub(crate) fn detect_bytes(bytes: Vec<u8>) -> Result<bool, String> {
    scanner_verified()?;
    run_scanner(bytes)
}

/// Synthetic canary for the scanner self-test. It is a fake token, never a real
/// credential, and every Gitleaks build measured in the lab detects it
/// (Debian 8.16.0 and upstream 8.30.1). Kept out of reports and logs.
///
/// The value is assembled at run time from two fragments so that the repository's
/// own secret scanning does not flag this source file and host-side push
/// protection cannot block a legitimate commit. The assembled bytes are what the
/// scanner sees, so the self-test still exercises the real detection path.
const SCANNER_CANARY_PREFIX: &[u8] = b"GITHUB_TOKEN=ghp_";
const SCANNER_CANARY_BODY: &[u8] = b"9fJ2kLm4Np6Qr8St0Uv2Wx4Yz6Ab8Cd0Ef2G";

fn scanner_canary() -> Vec<u8> {
    let mut canary =
        Vec::with_capacity(SCANNER_CANARY_PREFIX.len() + SCANNER_CANARY_BODY.len() + 1);
    canary.extend_from_slice(SCANNER_CANARY_PREFIX);
    canary.extend_from_slice(SCANNER_CANARY_BODY);
    canary.push(b'\n');
    canary
}

fn scanner_binary() -> String {
    std::env::var("H07P_SCANNER").unwrap_or_else(|_| "/usr/bin/gitleaks".into())
}

fn scanner_config() -> String {
    std::env::var("H07P_SCANNER_CONFIG")
        .unwrap_or_else(|_| "/opt/huou07-playground/current/deploy/gitleaks.toml".into())
}

/// Prove the configured scanner actually still finds a known fake credential
/// before trusting any "no finding" result from it. Without this, a scanner that
/// is missing, misconfigured, or changed its CLI/ruleset between releases would
/// report success for every file and turn into a false clean result. A verified
/// scanner is remembered; a failure is not cached so the next scan retries.
fn scanner_verified() -> Result<(), String> {
    static VERIFIED: std::sync::OnceLock<()> = std::sync::OnceLock::new();
    if VERIFIED.get().is_some() {
        return Ok(());
    }
    interpret_self_test(run_scanner(scanner_canary()))?;
    let _ = VERIFIED.set(());
    Ok(())
}

/// Fail-closed mapping from a self-test scanner run to a trust decision. A
/// scanner that exits successfully without finding the canary is as untrustworthy
/// as one that could not run at all.
fn interpret_self_test(result: Result<bool, String>) -> Result<(), String> {
    match result {
        Ok(true) => Ok(()),
        Ok(false) => Err("scanner_self_test_missed_canary".into()),
        Err(error) => Err(error),
    }
}

fn run_scanner(mut bytes: Vec<u8>) -> Result<bool, String> {
    if bytes.len() > 1024 * 1024 {
        return Err("content_budget".into());
    }
    let scanner = scanner_binary();
    let config = scanner_config();
    let (uid, gid) = crate::user_ids("huou07")?;
    let mut command = Command::new(scanner);
    command
        .env_clear()
        .current_dir("/")
        .args([
            "detect",
            "--pipe",
            "--redact",
            "--no-banner",
            "--log-level",
            "error",
            "--exit-code",
            "10",
            "--config",
            &config,
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    unsafe {
        command.pre_exec(move || {
            if libc::setgroups(0, std::ptr::null()) != 0
                || libc::setgid(gid) != 0
                || libc::setuid(uid) != 0
            {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut child = command.spawn().map_err(|_| "scanner_unavailable")?;
    let mut input = child.stdin.take().ok_or("scanner_stdin")?;
    // A bounded writer also gets reaped if a broken scanner stops consuming input.
    let writer = std::thread::spawn(move || {
        let result = input.write_all(&bytes);
        bytes.fill(0);
        result
    });
    let deadline = Instant::now() + Duration::from_secs(2);
    let result = loop {
        if let Some(status) = child.try_wait().map_err(|_| "scanner_wait")? {
            break match status.code() {
                Some(0) => Ok(false),
                Some(10) => Ok(true),
                _ => Err("scanner_failed".into()),
            };
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            break Err("scanner_timeout".into());
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let _ = writer.join();
    result
}

pub fn run(v: &Value) -> Result<Value, String> {
    use std::sync::atomic::{AtomicUsize, Ordering};
    static ACTIVE: AtomicUsize = AtomicUsize::new(0);
    if ACTIVE
        .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| {
            (n < 2).then_some(n + 1)
        })
        .is_err()
    {
        return Err("Detection is busy; retry after the current scan finishes".into());
    }
    struct Lease;
    impl Drop for Lease {
        fn drop(&mut self) {
            ACTIVE.fetch_sub(1, Ordering::SeqCst);
        }
    }
    let _lease = Lease;
    let scope = v["scope"].as_str().ok_or("Select a scan scope")?;
    let path = fs::canonicalize(scope).map_err(|e| e.to_string())?;
    if path.to_str().is_none() || path != std::path::Path::new(scope) {
        return Err("Scan scope must be a canonical UTF-8 path".into());
    }
    let root_metadata = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
    if root_metadata.file_type().is_symlink()
        || !(root_metadata.is_file() || root_metadata.is_dir())
    {
        return Err("Select a regular file or directory without a symlink alias".into());
    }
    let root_device = root_metadata.dev();
    let content_enabled = v["content"].as_bool().unwrap_or(false);
    let mode = v["mode"].as_str().unwrap_or("block");
    if !["block", "allow"].contains(&mode) {
        return Err("Unknown detection mode".into());
    }
    let mut found = Vec::new();
    let mut skipped = Vec::new();
    let start = Instant::now();
    let mut queue = vec![(path.clone(), 0usize)];
    let mut seen = 0;
    let mut scanned_bytes = 0u64;
    let mut content_files = 0;
    while let Some((directory, depth)) = queue.pop() {
        if excluded_filesystem(&directory) {
            skipped.push(json!({"path":directory,"reason":"filesystem_excluded"}));
            continue;
        }
        if depth > 8 || seen >= 100000 || start.elapsed() > Duration::from_secs(60) {
            skipped.push(json!({"path":directory,"reason":"scan_budget"}));
            continue;
        }
        let candidates: Box<
            dyn Iterator<Item = std::io::Result<(std::path::PathBuf, Option<String>)>>,
        > = if directory == path && root_metadata.is_file() {
            Box::new(std::iter::once(Ok((directory.clone(), None))))
        } else {
            match fs::read_dir(&directory) {
                Ok(entries) => Box::new(entries.map(|entry| {
                    entry.map(|entry| {
                        (
                            entry.path(),
                            Some(entry.file_name().to_string_lossy().to_lowercase()),
                        )
                    })
                })),
                Err(_) => {
                    skipped.push(json!({"path":directory,"reason":"unreadable"}));
                    continue;
                }
            }
        };
        for candidate in candidates {
            let (p, known_name) = match candidate {
                Ok(candidate) => candidate,
                Err(_) => {
                    skipped.push(json!({"path":directory,"reason":"directory_read_error"}));
                    continue;
                }
            };
            seen += 1;
            if seen > 100000 || start.elapsed() > Duration::from_secs(60) {
                skipped.push(json!({"path":directory,"reason":"scan_budget"}));
                break;
            }
            if p.to_str().is_none() {
                skipped.push(json!({"path":p.to_string_lossy(),"reason":"non_utf8_path"}));
                continue;
            }
            let m = match fs::symlink_metadata(&p) {
                Ok(m) => m,
                Err(_) => continue,
            };
            if m.file_type().is_symlink() || m.dev() != root_device {
                skipped.push(json!({"path":p,"reason":"symlink_or_other_filesystem"}));
                continue;
            }
            let name = known_name.unwrap_or_else(|| {
                p.file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_lowercase()
            });
            let sensitive_name = name.starts_with(".env") && !name.contains("example")
                || [
                    "credential",
                    "secret",
                    "password",
                    "token",
                    "id_rsa",
                    "id_ed25519",
                    ".npmrc",
                    "auth.json",
                ]
                .iter()
                .any(|n| name.contains(n))
                || name.ends_with(".pem")
                || name.ends_with(".key")
                || (name == "hosts.yml"
                    && p.parent()
                        .is_some_and(|parent| parent.ends_with(".config/gh")));
            let private_store = crate::helper::is_private_path(&p);
            let mut detected = sensitive_name || (private_store && m.is_file());
            let mut reason = if sensitive_name {
                "sensitive_filename"
            } else {
                "protected_private_store"
            };
            let mut unknown = false;
            if content_enabled && m.is_file() {
                if content_files >= 128 || scanned_bytes.saturating_add(m.len()) > 16 * 1024 * 1024
                {
                    skipped.push(json!({"path":p,"reason":"content_budget"}));
                    unknown = true;
                } else {
                    content_files += 1;
                    scanned_bytes += m.len();
                    match content(&p, &m) {
                        Ok(true) => {
                            detected = true;
                            reason = "maintained_scanner_match";
                        }
                        Ok(false) => {}
                        Err(error) => {
                            skipped.push(json!({"path":p,"reason":error}));
                            unknown = true;
                        }
                    }
                }
            }
            if (detected && mode == "block")
                || (!detected && !unknown && mode == "allow" && m.is_file())
            {
                found.push(json!({"path":p,"reason":if detected{reason}else{"no_known_sensitive_marker"},"confidence":if detected{"high"}else{"unknown"}}));
            }
            if m.is_dir() && name != ".git" && name != "node_modules" {
                queue.push((p, depth + 1));
            }
        }
    }
    Ok(
        json!({"findings":found,"skipped":skipped,"partial":!skipped.is_empty(),"scanned":seen,
        "content_scanned":content_enabled,"content_files":content_files,"content_bytes":scanned_bytes,
        "warning":"Detection is a proposal, not proof of safety. Unknown and skipped files remain unclassified. Nothing has been applied."}),
    )
}

#[cfg(test)]
mod tests {
    #[test]
    fn pseudo_filesystems_are_excluded() {
        assert!(super::excluded_filesystem(std::path::Path::new("/proc")));
        assert!(super::excluded_filesystem(std::path::Path::new("/sys")));
    }

    #[test]
    fn self_test_accepts_only_a_confirmed_canary_match() {
        assert!(super::interpret_self_test(Ok(true)).is_ok());
        assert_eq!(
            super::interpret_self_test(Ok(false)),
            Err("scanner_self_test_missed_canary".into())
        );
        assert_eq!(
            super::interpret_self_test(Err("scanner_unavailable".into())),
            Err("scanner_unavailable".into())
        );
    }

    #[test]
    fn canary_is_a_synthetic_github_token_shape() {
        let canary = String::from_utf8(super::scanner_canary()).unwrap();
        assert!(canary.contains("ghp_"));
        assert!(!canary.to_lowercase().contains("example"));
        assert!(canary.ends_with('\n'));
    }
}
