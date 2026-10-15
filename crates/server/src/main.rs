#[cfg(target_os = "linux")]
mod api;
#[cfg(target_os = "linux")]
mod broker;
#[cfg(target_os = "linux")]
mod files;
#[cfg(target_os = "linux")]
mod helper;
#[cfg(target_os = "linux")]
mod relays;
#[cfg(target_os = "linux")]
mod sandbox;
#[cfg(target_os = "linux")]
mod scan;
mod telemetry;
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
            let mut s = std::os::unix::net::UnixStream::connect("/run/h07p/broker.sock")
                .map_err(|_| "Worker broker unavailable")?;
            let v = if args[0] == "request" {
                serde_json::json!({"op":"request","operation":"read","path":args.get(1).ok_or("Select a path")?})
            } else {
                serde_json::json!({"op":"redeem","id":args.get(1).ok_or("Select an approval id")?})
            };
            writeln!(s, "{v}").map_err(|_| "Broker request failed")?;
            let mut line = String::new();
            std::io::BufReader::new(s)
                .read_line(&mut line)
                .map_err(|_| "Broker response failed")?;
            print!("{line}");
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
