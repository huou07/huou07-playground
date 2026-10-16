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

pub(crate) fn detect_bytes(mut bytes: Vec<u8>) -> Result<bool, String> {
    if bytes.len() > 1024 * 1024 {
        return Err("content_budget".into());
    }
    let scanner = std::env::var("H07P_SCANNER").unwrap_or_else(|_| "/usr/bin/gitleaks".into());
    let config = std::env::var("H07P_SCANNER_CONFIG")
        .unwrap_or_else(|_| "/opt/huou07-playground/current/deploy/gitleaks.toml".into());
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
    if path.to_str().is_none() {
        return Err("Scan scope must be a UTF-8 path".into());
    }
    if !path.starts_with("/home/huou07") && !path.starts_with("/tmp") {
        return Err("Select an owner home or synthetic temporary scope".into());
    }
    if crate::helper::protected(&path, false) {
        return Err("Select ordinary owner data outside protected runtime and credentials".into());
    }
    let content_enabled = v["content"].as_bool().unwrap_or(false);
    let mode = v["mode"].as_str().unwrap_or("block");
    if !["block", "allow"].contains(&mode) {
        return Err("Unknown detection mode".into());
    }
    let mut found = Vec::new();
    let mut skipped = Vec::new();
    let start = Instant::now();
    let mut queue = vec![(path, 0usize)];
    let mut seen = 0;
    let mut scanned_bytes = 0u64;
    let mut content_files = 0;
    while let Some((p, depth)) = queue.pop() {
        if excluded_filesystem(&p) {
            skipped.push(json!({"path":p,"reason":"filesystem_excluded"}));
            continue;
        }
        if depth > 8 || seen >= 10000 || start.elapsed() > Duration::from_secs(10) {
            skipped.push(json!({"path":p,"reason":"scan_budget"}));
            continue;
        }
        let entries = match fs::read_dir(&p) {
            Ok(e) => e,
            Err(_) => {
                skipped.push(json!({"path":p,"reason":"unreadable"}));
                continue;
            }
        };
        for entry in entries.flatten() {
            seen += 1;
            if seen > 10000 || start.elapsed() > Duration::from_secs(10) {
                skipped.push(json!({"path":p,"reason":"scan_budget"}));
                break;
            }
            let p = entry.path();
            if p.to_str().is_none() {
                skipped.push(json!({"path":p.to_string_lossy(),"reason":"non_utf8_path"}));
                continue;
            }
            let m = match fs::symlink_metadata(&p) {
                Ok(m) => m,
                Err(_) => continue,
            };
            if m.file_type().is_symlink() || crate::helper::protected(&p, false) {
                skipped.push(json!({"path":p,"reason":"symlink_or_protected"}));
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_lowercase();
            let sensitive = name.starts_with(".env") && !name.contains("example")
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
                || name.ends_with(".key");
            let mut detected = sensitive;
            let mut reason = "sensitive_filename";
            let mut unknown = false;
            if content_enabled && m.is_file() && !sensitive {
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
            if m.is_dir() && !sensitive && !name.starts_with('.') && name != "node_modules" {
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
}
