#[cfg(target_os = "linux")]
mod api;
#[cfg(target_os = "linux")]
mod app_logins;
#[cfg(target_os = "linux")]
mod broker;
#[cfg(target_os = "linux")]
mod files;
#[cfg(target_os = "linux")]
mod guard;
#[cfg(target_os = "linux")]
mod helper;
#[cfg(target_os = "linux")]
mod native_proxy;
mod redact;
#[cfg(target_os = "linux")]
mod relays;
#[cfg(target_os = "linux")]
mod sandbox;
#[cfg(target_os = "linux")]
mod scan;
#[cfg(target_os = "linux")]
mod sensitive;
mod telemetry;
#[cfg(target_os = "linux")]
mod vpn_apps;
#[cfg(target_os = "linux")]
mod worker_setup;
use std::{io::Read, path::PathBuf};
pub fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
pub fn random_token() -> Result<String, String> {
    let mut bytes = [0; 32];
    std::fs::File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut bytes))
        .map_err(|_| "Random source unavailable")?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}
pub fn user_ids(name: &str) -> Result<(u32, u32), String> {
    let name = std::ffi::CString::new(name).map_err(|_| "Invalid account")?;
    let mut buf = vec![0u8; 16384];
    let mut entry: libc::passwd = unsafe { std::mem::zeroed() };
    let mut result = std::ptr::null_mut();
    let rc = unsafe {
        libc::getpwnam_r(
            name.as_ptr(),
            &mut entry,
            buf.as_mut_ptr() as *mut _,
            buf.len(),
            &mut result,
        )
    };
    if rc != 0 || result.is_null() {
        Err("Required account is missing".into())
    } else {
        Ok((entry.pw_uid, entry.pw_gid))
    }
}
fn main() {
    if let Err(e) = run() {
        eprintln!("H07P: {e}");
        std::process::exit(1)
    }
}
#[cfg(not(target_os = "linux"))]
fn run() -> Result<(), String> {
    Err("H07P host server: Linux is supported; other platforms Coming soon".into())
}
#[cfg(target_os = "linux")]
fn run() -> Result<(), String> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    match args.first().map(String::as_str) {
        Some("helper") => return helper::run(),
        Some("worker") => {
            return sandbox::run(
                args.get(1).ok_or("Select dsh, codex or opencode")?,
                &args[2..],
            )
        }
        Some("fs-actor") => {
            if let Err(e) = files::actor() {
                if !files::RESPONSE_STARTED.load(std::sync::atomic::Ordering::SeqCst) {
                    println!("{}", serde_json::json!({"ok":false,"error":e}));
                }
                return Err("File operation failed".into());
            }
            return Ok(());
        }
        Some("request") | Some("redeem") => {
            use std::io::{BufRead, Write};
            let v = if args[0] == "request" {
                let first = args.get(1).ok_or(
                    "Usage: request read|list|write|create|delete /absolute/path [--stdin]",
                )?;
                let (operation, path) = if first.starts_with('/') && args.len() == 2 {
                    ("read", first)
                } else {
                    if !["read", "list", "write", "create", "delete"].contains(&first.as_str()) {
                        return Err("Unsupported broker operation".into());
                    }
                    (
                        first.as_str(),
                        args.get(2).ok_or("Select an absolute target")?,
                    )
                };
                let mut value =
                    serde_json::json!({"op":"request","operation":operation,"path":path});
                if ["write", "create"].contains(&operation) {
                    if args.get(3).map(String::as_str) != Some("--stdin") || args.len() != 4 {
                        return Err("Provide the exact UTF-8 write content through --stdin (at most 64 KiB)".into());
                    }
                    let mut content = String::new();
                    std::io::stdin()
                        .take(65537)
                        .read_to_string(&mut content)
                        .map_err(|_| "Write content must be UTF-8")?;
                    if content.len() > 65536 {
                        return Err("Write content exceeds 64 KiB".into());
                    }
                    value["content"] = content.into();
                } else if args.len() > 3 {
                    return Err("Unexpected broker arguments".into());
                }
                value
            } else {
                if args.len() != 2 {
                    return Err("Usage: redeem APPROVAL_ID".into());
                }
                serde_json::json!({"op":"redeem","id":args.get(1).ok_or("Select an approval id")?})
            };
            let socket = std::env::var("H07P_BROKER_SOCKET")
                .unwrap_or_else(|_| "/run/h07p/broker.sock".into());
            let mut s = std::os::unix::net::UnixStream::connect(socket)
                .map_err(|_| "Worker broker unavailable")?;
            s.set_read_timeout(Some(std::time::Duration::from_secs(40)))
                .map_err(|_| "Broker timeout unavailable")?;
            writeln!(s, "{v}").map_err(|_| "Broker request failed")?;
            let mut line = String::new();
            std::io::BufReader::new(s)
                .read_line(&mut line)
                .map_err(|_| "Broker response failed")?;
            print!("{line}");
            if serde_json::from_str::<serde_json::Value>(&line)
                .map(|v| v["ok"] != true)
                .unwrap_or(true)
            {
                return Err("Broker operation was not authorized or did not complete".into());
            }
            return Ok(());
        }
        Some("--help") => {
            println!("H07P Linux owner dashboard\nWorker broker: request read|list|write|create|delete /absolute/path [--stdin]\nOwner decision appears in Permissions; then redeem APPROVAL_ID.\nWrites are UTF-8, at most 64 KiB, fixed at request time. Execute is unsupported.");
            return Ok(());
        }
        None => {}
        _ => return Err("Unknown H07P mode".into()),
    }
    let host = std::env::var("HOST").unwrap_or_else(|_| "127.0.0.1".into());
    if !["127.0.0.1", "::1", "localhost"].contains(&host.as_str()) {
        return Err("Server binds loopback; root helper provides device-bound VPN relays".into());
    }
    let port = std::env::var("PORT")
        .unwrap_or_else(|_| "8765".into())
        .parse::<u16>()
        .map_err(|_| "Invalid port")?;
    if port == 0 {
        return Err("Port must be nonzero".into());
    }
    let root = std::env::var_os("STATIC_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../web/static"));
    if !root.is_dir() {
        return Err("Static files unavailable".into());
    }
    let runtime = tokio::runtime::Runtime::new().map_err(|_| "Async runtime unavailable")?;
    runtime.block_on(async {
        let router = api::app(root)?;
        let listener = tokio::net::TcpListener::bind((
            if host == "localhost" {
                "127.0.0.1"
            } else {
                &host
            },
            port,
        ))
        .await
        .map_err(|_| "Dashboard port is unavailable")?;
        axum::serve(listener, router)
            .with_graceful_shutdown(async {
                let _ = tokio::signal::ctrl_c().await;
            })
            .await
            .map_err(|_| "HTTP server failed".to_string())
    })
}

/// Shared cap for blocking control clients and relay connections.
pub fn bounded_spawn(task: impl FnOnce() + Send + 'static) {
    use std::sync::atomic::{AtomicUsize, Ordering};
    static ACTIVE: AtomicUsize = AtomicUsize::new(0);
    if ACTIVE
        .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| {
            (n < 128).then_some(n + 1)
        })
        .is_err()
    {
        return;
    }
    struct Lease;
    impl Drop for Lease {
        fn drop(&mut self) {
            ACTIVE.fetch_sub(1, Ordering::SeqCst);
        }
    }
    let lease = Lease;
    let _ = std::thread::Builder::new().spawn(move || {
        let _lease = lease;
        task();
    });
}
