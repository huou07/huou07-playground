//! Native worker launcher. Call before creating any threads or Tokio runtime.
use serde::Deserialize;
use std::path::{Path, PathBuf};

const HOME: &str = "/home/huou07";

#[derive(Deserialize)]
struct LaunchPolicy {
    #[serde(default = "default_preset")]
    preset: String,
    #[serde(default = "default_workspace")]
    workspace: PathBuf,
}

fn default_preset() -> String {
    "none".into()
}
fn default_workspace() -> PathBuf {
    PathBuf::from("/home/huou07/Projects")
}
fn checked_policy(bytes: &[u8]) -> Result<LaunchPolicy, String> {
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|_| "Worker policy is malformed")?;
    if !value["revision"].is_null()
        && (value["revision"].as_u64().is_none()
            || value["revision"].as_u64() != value["enforced_revision"].as_u64())
    {
        return Err("Policy enforcement is pending; worker launch is blocked".into());
    }
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    if value["rules"].as_array().is_some_and(|rules| {
        rules
            .iter()
            .any(|r| r["expires_at"].as_u64().is_some_and(|t| t <= now))
    }) {
        return Err(
            "Expired policy needs reconciliation; retry after the control service applies it"
                .into(),
        );
    }
    serde_json::from_value(value).map_err(|_| "Worker policy is malformed".into())
}
fn worker_policy(bytes: &[u8], worker: &str) -> Result<LaunchPolicy, String> {
    checked_policy(bytes)?;
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|_| "Worker policy is malformed")?;
    let specific = &value["worker_settings"][worker];
    if specific["enabled"] == false {
        return Err("This managed worker is disabled".into());
    }
    let preset = specific
        .get("preset")
        .or_else(|| value.get("preset"))
        .cloned()
        .unwrap_or_else(|| serde_json::json!("none"));
    let workspace = specific
        .get("workspace")
        .or_else(|| value.get("workspace"))
        .cloned()
        .unwrap_or_else(|| serde_json::json!(default_workspace()));
    serde_json::from_value(serde_json::json!({"preset":preset,"workspace":workspace}))
        .map_err(|_| "Worker policy is malformed".into())
}

fn native_paths(harness: &str) -> Result<Vec<PathBuf>, String> {
    let relative: &[&str] = match harness {
        "dsh" => &[".dsh"],
        "codex" => &[".codex"],
        "opencode" => &[
            ".config/opencode",
            ".local/share/opencode",
            ".local/state/opencode",
            ".cache/opencode",
        ],
        _ => return Err("Unknown native harness".into()),
    };
    Ok(relative
        .iter()
        .map(|entry| Path::new(HOME).join(entry))
        .collect())
}

fn restricted(policy: &LaunchPolicy) -> Result<bool, String> {
    match policy.preset.as_str() {
        "strict" | "balance" => Ok(true),
        "none" | "minimal" => Ok(false),
        _ => Err("Unsupported worker policy preset".into()),
    }
}

#[cfg(target_os = "linux")]
mod linux {
    use super::*;
    use std::{
        env,
        ffi::CString,
        fs,
        os::unix::{fs::MetadataExt, process::CommandExt},
        process::Command,
    };

    const READ: u64 = (1 << 0) | (1 << 2) | (1 << 3);
    const WRITE: u64 = (1 << 1)
        | (1 << 4)
        | (1 << 5)
        | (1 << 7)
        | (1 << 8)
        | (1 << 9)
        | (1 << 10)
        | (1 << 12)
        | (1 << 13)
        | (1 << 14);
    const HANDLED: u64 = (1 << 15) - 1;

    #[repr(C)]
    struct Ruleset {
        handled_access_fs: u64,
    }
    #[repr(C, packed)]
    struct Beneath {
        allowed_access: u64,
        parent_fd: i32,
    }

    fn failure(operation: &str) -> String {
        format!("{operation}: {}", std::io::Error::last_os_error())
    }

    fn identity(harness: &str) -> Result<(u32, u32), String> {
        let account = CString::new(format!("{harness}-worker")).map_err(|_| "Invalid harness")?;
        // The launcher has no threads; libc's passwd record is copied before further calls.
        let record = unsafe { libc::getpwnam(account.as_ptr()) };
        if record.is_null() {
            return Err("Native worker account is missing".into());
        }
        let uid = unsafe { (*record).pw_uid };
        let gid = unsafe { (*record).pw_gid };
        if uid == 0 || gid == 0 {
            return Err("Worker identity must be unprivileged".into());
        }
        Ok((uid, gid))
    }

    fn private_directory(path: &Path, uid: u32, gid: u32) -> Result<(), String> {
        match fs::symlink_metadata(path) {
            Ok(meta) => {
                if !meta.is_dir() || meta.file_type().is_symlink() || meta.uid() != uid {
                    return Err("Native or temporary directory has an unexpected owner/type".into());
                }
                return Ok(());
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err("Cannot inspect worker directory".into()),
        }
        // Parent directories must already be provisioned by the trusted installation.
        let text = CString::new(path.as_os_str().as_encoded_bytes())
            .map_err(|_| "Invalid worker directory")?;
        if unsafe { libc::mkdir(text.as_ptr(), 0o700) } != 0 {
            return Err(failure("Create worker directory"));
        }
        let fd = unsafe {
            libc::open(
                text.as_ptr(),
                libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(failure("Open worker directory"));
        }
        let changed = unsafe { libc::fchown(fd, uid, gid) };
        let error = if changed != 0 {
            Some(failure("Set worker directory ownership"))
        } else {
            None
        };
        unsafe {
            libc::close(fd);
        }
        if let Some(error) = error {
            return Err(error);
        }
        Ok(())
    }

    fn landlock(
        workspace: &Path,
        native: &[PathBuf],
        temporary: &Path,
        dsh_web: bool,
    ) -> Result<(), String> {
        let abi = unsafe {
            libc::syscall(
                libc::SYS_landlock_create_ruleset,
                std::ptr::null::<u8>(),
                0,
                1,
            )
        };
        if abi < 3 {
            return Err("Strict/balance requires Linux Landlock ABI 3 or newer".into());
        }
        let handled = HANDLED | if abi >= 5 { 1 << 15 } else { 0 };
        let attributes = Ruleset {
            handled_access_fs: handled,
        };
        let fd = unsafe {
            libc::syscall(
                libc::SYS_landlock_create_ruleset,
                &attributes,
                std::mem::size_of::<Ruleset>(),
                0,
            )
        } as i32;
        if fd < 0 {
            return Err(failure("Create Landlock ruleset"));
        }
        let result = (|| {
            let mut paths: Vec<(PathBuf, bool)> = [
                "/usr",
                "/bin",
                "/sbin",
                "/lib",
                "/lib64",
                "/etc/ssl",
                "/etc/ld.so.cache",
                "/etc/resolv.conf",
                "/etc/hosts",
                "/etc/passwd",
                "/etc/group",
                "/etc/nsswitch.conf",
                "/dev/urandom",
                "/dev/random",
                "/proc/self",
                "/home/huou07/.local/bin",
                "/home/huou07/.local/lib",
                "/home/huou07/.cargo/bin",
                "/home/huou07/.rustup",
                "/opt/huou07-playground/current/bin/h07p-server",
            ]
            .iter()
            .map(|p| (PathBuf::from(p), false))
            .collect();
            paths.extend(
                ["/dev/null", "/dev/tty", "/dev/pts"]
                    .iter()
                    .map(|p| (PathBuf::from(p), true)),
            );
            if dsh_web {
                paths.push((PathBuf::from("/run/huou07-dsh-link"), true));
            }
            paths.push((workspace.to_path_buf(), true));
            paths.push((temporary.to_path_buf(), true));
            paths.extend(native.iter().cloned().map(|p| (p, true)));
            for (path, writable) in paths {
                let metadata = match fs::metadata(&path) {
                    Ok(value) => value,
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                    Err(_) => return Err("Cannot inspect Landlock runtime path".into()),
                };
                let text = CString::new(path.as_os_str().as_encoded_bytes())
                    .map_err(|_| "Invalid runtime path")?;
                let parent = unsafe { libc::open(text.as_ptr(), libc::O_PATH | libc::O_CLOEXEC) };
                if parent < 0 {
                    return Err(failure("Open Landlock runtime path"));
                }
                let mut access = READ | if writable { WRITE } else { 0 };
                if !metadata.is_dir() {
                    access &= (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14);
                }
                if abi >= 5 && writable && path.starts_with("/dev") {
                    access |= 1 << 15;
                }
                let rule = Beneath {
                    allowed_access: access,
                    parent_fd: parent,
                };
                let added = unsafe { libc::syscall(libc::SYS_landlock_add_rule, fd, 1, &rule, 0) };
                let error = if added != 0 {
                    Some(failure("Add Landlock runtime rule"))
                } else {
                    None
                };
                unsafe {
                    libc::close(parent);
                }
                if let Some(error) = error {
                    return Err(error);
                }
            }
            if unsafe { libc::syscall(libc::SYS_landlock_restrict_self, fd, 0) } != 0 {
                return Err(failure("Apply Landlock ruleset"));
            }
            Ok(())
        })();
        unsafe {
            libc::close(fd);
        }
        result
    }

    pub fn run(harness: &str, args: &[String]) -> Result<(), String> {
        if unsafe { libc::geteuid() } != 0 {
            return Err("Worker launch requires the root launcher".into());
        }
        let native = native_paths(harness)?;
        let control = env::var_os("H07P_CONTROL_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/var/lib/h07p-control"));
        let policy = match fs::read(control.join("policy.json")) {
            Ok(bytes) => worker_policy(&bytes, &format!("{harness}-worker"))?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => LaunchPolicy {
                preset: default_preset(),
                workspace: default_workspace(),
            },
            Err(_) => return Err("Worker policy is unreadable".into()),
        };
        let strict = restricted(&policy)?;
        let workspace = policy
            .workspace
            .canonicalize()
            .map_err(|_| "Worker workspace is missing")?;
        if !workspace.is_dir() {
            return Err("Worker workspace must be a directory".into());
        }
        let (uid, gid) = identity(harness)?;
        for path in &native {
            private_directory(path, uid, gid)?;
        }
        let temporary = PathBuf::from(format!("/tmp/h07p-{uid}"));
        private_directory(&temporary, uid, gid)?;
        if fs::metadata(&temporary)
            .map_err(|_| "Cannot inspect worker temporary directory")?
            .mode()
            & 0o077
            != 0
        {
            return Err("Worker temporary directory must be private (mode 0700)".into());
        }
        let current = env::current_dir()
            .ok()
            .filter(|p| p.starts_with(HOME))
            .unwrap_or_else(|| workspace.clone());
        let web = args.first().is_some_and(|value| value == "--web");
        if web && harness == "codex" {
            return Err("Codex has no managed web service".into());
        }
        let mut command = if web && harness == "dsh" {
            let mut command = Command::new("/usr/bin/python3");
            command.arg("/usr/local/libexec/h07p/dsh-dashboard-launcher.py");
            command
        } else {
            let mut command = Command::new(Path::new(HOME).join(".local/bin").join(harness));
            if web && harness == "opencode" {
                command.args(["web", "--hostname", "127.0.0.1", "--port", "4097"]);
            }
            command
        };
        command.args(if web { &args[1..] } else { args });
        command
            .env_clear()
            .current_dir(current)
            .env("HOME", HOME)
            .env("USER", format!("{harness}-worker"))
            .env("LOGNAME", format!("{harness}-worker"))
            .env("DSH_HOME", format!("{HOME}/.dsh"))
            .env("CODEX_HOME", format!("{HOME}/.codex"))
            .env(
                "PATH",
                format!("{HOME}/.local/bin:{HOME}/.cargo/bin:/usr/local/bin:/usr/bin:/bin"),
            )
            .env("TMPDIR", &temporary)
            .env("NPM_CONFIG_USERCONFIG", native[0].join("npmrc"))
            .env("GIT_CONFIG_COUNT", "1")
            .env("GIT_CONFIG_KEY_0", "safe.directory")
            .env("GIT_CONFIG_VALUE_0", format!("{HOME}/*"))
            .env(
                "TERM",
                env::var("TERM")
                    .ok()
                    .filter(|v| v.len() < 128 && !v.contains('\0'))
                    .unwrap_or_else(|| "xterm-256color".into()),
            );
        if web && harness == "opencode" {
            for key in ["OPENCODE_SERVER_USERNAME", "OPENCODE_SERVER_PASSWORD"] {
                if let Some(value) = env::var_os(key) {
                    command.env(key, value);
                }
            }
        }
        // Dropping IDs permanently is independent of Landlock; none/minimal retain DAC/ACL.
        if unsafe { libc::setgroups(0, std::ptr::null()) } != 0 {
            return Err(failure("Clear worker supplementary groups"));
        }
        if unsafe { libc::setresgid(gid, gid, gid) } != 0 {
            return Err(failure("Set permanent worker GID"));
        }
        if unsafe { libc::setresuid(uid, uid, uid) } != 0 {
            return Err(failure("Set permanent worker UID"));
        }
        if unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0 {
            return Err(failure("Set no_new_privs"));
        }
        if strict {
            landlock(&workspace, &native, &temporary, web && harness == "dsh")?;
        }
        if unsafe { libc::syscall(libc::SYS_close_range, 3u32, u32::MAX, 0u32) } != 0 {
            return Err(failure("Close inherited worker descriptors"));
        }
        if web {
            // Preserve interactive CLI terminal behavior; web-service logs are
            // classified in bounded buffers before systemd/journald receives them.
            let mut child = command
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .spawn()
                .map_err(|_| "Native web worker could not start")?;
            let stdout = child.stdout.take().ok_or("Native output unavailable")?;
            let stderr = child
                .stderr
                .take()
                .ok_or("Native error output unavailable")?;
            let out = std::thread::spawn(move || crate::redact::stream(stdout, std::io::stdout()));
            let err = std::thread::spawn(move || crate::redact::stream(stderr, std::io::stderr()));
            let status = child.wait().map_err(|_| "Native web worker wait failed")?;
            out.join()
                .map_err(|_| "Log redaction worker failed")?
                .map_err(|_| "Log output failed")?;
            err.join()
                .map_err(|_| "Log redaction worker failed")?
                .map_err(|_| "Log output failed")?;
            return if status.success() {
                Ok(())
            } else {
                Err("Native web worker exited; inspect the redacted service log".into())
            };
        }
        Err(format!("Native worker exec failed: {}", command.exec()))
    }
}

#[cfg(target_os = "linux")]
pub use linux::run;
#[cfg(not(target_os = "linux"))]
pub fn run(_: &str, _: &[String]) -> Result<(), String> {
    Err("Native worker launch requires Linux".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_stores_are_per_harness() {
        assert_eq!(
            native_paths("dsh").unwrap(),
            vec![PathBuf::from("/home/huou07/.dsh")]
        );
        assert_eq!(
            native_paths("codex").unwrap(),
            vec![PathBuf::from("/home/huou07/.codex")]
        );
        assert_eq!(native_paths("opencode").unwrap().len(), 4);
        assert!(native_paths("unknown").is_err());
    }
    #[test]
    fn unknown_policy_cannot_relax_worker() {
        let policy = |preset: &str| LaunchPolicy {
            preset: preset.into(),
            workspace: default_workspace(),
        };
        assert!(!restricted(&policy("none")).unwrap());
        assert!(restricted(&policy("strict")).unwrap());
        assert!(restricted(&policy("balance")).unwrap());
        assert!(restricted(&policy("custom-typo")).is_err());
        let absent: LaunchPolicy = serde_json::from_str("{}").unwrap();
        assert_eq!(absent.preset, "none");
    }
    #[test]
    fn pending_or_expired_policy_cannot_launch() {
        assert!(checked_policy(br#"{"revision":2,"enforced_revision":null}"#).is_err());
        assert!(checked_policy(br#"{"revision":2,"enforced_revision":1}"#).is_err());
        assert!(checked_policy(
            br#"{"revision":2,"enforced_revision":2,"rules":[{"expires_at":1}]}"#
        )
        .is_err());
        assert!(checked_policy(br#"{"revision":2,"enforced_revision":2,"rules":[]}"#).is_ok());
    }
    #[test]
    fn individual_worker_settings_do_not_change_other_workers() {
        let bytes=br#"{"revision":3,"enforced_revision":3,"preset":"none","workspace":"/home/huou07/Projects","worker_settings":{"dsh-worker":{"preset":"strict","workspace":"/home/huou07/Projects/selected"},"codex-worker":{"enabled":false}}}"#;
        let selected = worker_policy(bytes, "dsh-worker").unwrap();
        assert_eq!(selected.preset, "strict");
        assert!(selected.workspace.ends_with("selected"));
        assert_eq!(
            worker_policy(bytes, "opencode-worker").unwrap().preset,
            "none"
        );
        assert!(worker_policy(bytes, "codex-worker").is_err());
    }
}
