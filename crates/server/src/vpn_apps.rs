//! Owner-selected VPN relays. App authentication remains entirely with the app.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{Shutdown, SocketAddr, TcpListener, TcpStream},
    os::{
        fd::AsRawFd,
        unix::{fs::OpenOptionsExt, net::UnixStream},
    },
    path::PathBuf,
    sync::{Arc, Mutex, OnceLock},
    time::Duration,
};
#[derive(Clone, Serialize, Deserialize)]
struct Config {
    name: String,
    target: SocketAddr,
    port: u16,
}
#[derive(Default)]
struct Connections {
    stopped: bool,
    next: u64,
    sockets: BTreeMap<u64, (TcpStream, TcpStream)>,
}
struct Relay {
    wake: UnixStream,
    connections: Arc<Mutex<Connections>>,
    thread: Option<std::thread::JoinHandle<()>>,
}
impl Drop for Relay {
    fn drop(&mut self) {
        let mut active = self.connections.lock().unwrap_or_else(|e| e.into_inner());
        active.stopped = true;
        for (a, b) in active.sockets.values() {
            let _ = a.shutdown(Shutdown::Both);
            let _ = b.shutdown(Shutdown::Both);
        }
        drop(active);
        let _ = self.wake.write_all(&[1]);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
type Relays = BTreeMap<u16, Relay>;
fn manager() -> &'static Mutex<Relays> {
    static MANAGER: OnceLock<Mutex<Relays>> = OnceLock::new();
    MANAGER.get_or_init(|| Mutex::new(BTreeMap::new()))
}
fn config_path() -> PathBuf {
    std::env::var_os("H07P_CONTROL_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| "/var/lib/h07p-control".into())
        .join("vpn-apps.json")
}
fn save(config: &[Config]) -> Result<(), String> {
    let path = config_path();
    let temporary = path.with_extension(crate::random_token()?);
    let bytes = serde_json::to_vec(config).map_err(|_| "VPN configuration encoding failed")?;
    let result = (|| -> std::io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, &path)?;
        std::fs::File::open(path.parent().unwrap())?.sync_all()
    })();
    if result.is_err() {
        let _ = fs::remove_file(temporary);
    }
    result.map_err(|_| "Cannot save VPN configuration".into())
}
fn builtin_port(port: u16) -> bool {
    let value: Value =
        serde_json::from_str(include_str!("../../../deploy/private-services.json")).unwrap();
    value["services"]
        .as_array()
        .unwrap()
        .iter()
        .any(|s| s["wireguard_port"] == port)
}
fn validate(config: &Config) -> Result<(), String> {
    if config.name.trim().is_empty()
        || config.name.chars().count() > 60
        || config.name.chars().any(char::is_control)
        || config.port < 1024
        || builtin_port(config.port)
        || config.target.port() == 4097
        || config.target.port() == 0
        || config.target.ip().is_unspecified()
        || config.target.ip().is_multicast()
    {
        return Err("Select a name, a host service and an unused VPN port from 1024 to 65535. Built-in relays and internal backends are reserved.".into());
    }
    Ok(())
}
fn start(config: Config, address: SocketAddr, interface: Option<&str>) -> Result<Relay, String> {
    let listener = TcpListener::bind(address)
        .map_err(|_| "VPN port unavailable. Check WireGuard and choose an unused port.")?;
    if let Some(interface) = interface {
        let interface = std::ffi::CString::new(interface).map_err(|_| "Invalid interface")?;
        if unsafe {
            libc::setsockopt(
                listener.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_BINDTODEVICE,
                interface.as_ptr().cast(),
                interface.as_bytes_with_nul().len() as _,
            )
        } != 0
        {
            return Err("Cannot bind the relay exclusively to WireGuard".into());
        }
    }
    listener
        .set_nonblocking(true)
        .map_err(|_| "Cannot initialize VPN listener")?;
    let (wake, mut cancellation) =
        UnixStream::pair().map_err(|_| "Cannot initialize VPN cancellation")?;
    let connections = Arc::new(Mutex::new(Connections::default()));
    let active = connections.clone();
    let target = config.target;
    let thread = std::thread::spawn(move || {
        let mut descriptors = [
            libc::pollfd {
                fd: listener.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: cancellation.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        loop {
            let ready = unsafe { libc::poll(descriptors.as_mut_ptr(), 2, -1) };
            if ready < 0 {
                if std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted {
                    continue;
                }
                break;
            }
            if descriptors[1].revents != 0 {
                let _ = cancellation.read(&mut [0]);
                break;
            }
            if descriptors[0].revents & libc::POLLIN == 0 {
                break;
            }
            if let Ok((client, _)) = listener.accept() {
                let active = active.clone();
                crate::bounded_spawn(move || {
                    let Ok(mut backend) =
                        TcpStream::connect_timeout(&target, Duration::from_secs(3))
                    else {
                        return;
                    };
                    let mut client = client;
                    let (Ok(mut a), Ok(mut b), Ok(held_client), Ok(held_backend)) = (
                        client.try_clone(),
                        backend.try_clone(),
                        client.try_clone(),
                        backend.try_clone(),
                    ) else {
                        return;
                    };
                    for socket in [&client, &backend] {
                        let _ = socket.set_write_timeout(Some(Duration::from_secs(180)));
                        let _ = socket.set_read_timeout(Some(Duration::from_secs(180)));
                    }
                    let id = {
                        let mut state = active.lock().unwrap_or_else(|e| e.into_inner());
                        if state.stopped {
                            return;
                        }
                        state.next = state.next.wrapping_add(1);
                        let id = state.next;
                        state.sockets.insert(id, (held_client, held_backend));
                        id
                    };
                    std::thread::scope(|scope| {
                        scope.spawn(move || {
                            let _ = std::io::copy(&mut a, &mut b);
                            let _ = b.shutdown(Shutdown::Write);
                        });
                        let _ = std::io::copy(&mut backend, &mut client);
                        let _ = client.shutdown(Shutdown::Write);
                    });
                    active
                        .lock()
                        .unwrap_or_else(|e| e.into_inner())
                        .sockets
                        .remove(&id);
                });
            }
        }
    });
    Ok(Relay {
        wake,
        connections,
        thread: Some(thread),
    })
}
fn firewall(port: u16, add: bool) -> Result<(), String> {
    let Some(status) = crate::telemetry::command("ufw", &["status"], 3) else {
        return Ok(());
    };
    if !status.lines().any(|line| line.trim() == "Status: active") {
        return Ok(());
    }
    let port = port.to_string();
    let added = crate::telemetry::command("ufw", &["show", "added"], 3)
        .ok_or("Cannot inspect existing firewall rules")?;
    let matching: Vec<_> = added
        .lines()
        .filter(|line| {
            let words: Vec<_> = line.split_whitespace().collect();
            words.windows(2).any(|w| w == ["port", port.as_str()])
                && words.windows(2).any(|w| w == ["on", "wg0"])
                && words.windows(2).any(|w| w == ["to", "10.8.0.1"])
        })
        .collect();
    if add && !matching.is_empty() {
        return Err("A firewall rule already uses this relay port. Choose another port to preserve the existing rule.".into());
    }
    if !add && !matching.iter().any(|line| line.contains("h07p-vpn-app")) {
        return Ok(());
    }
    let mut args = vec!["--force"];
    if !add {
        args.push("delete");
    }
    args.extend([
        "allow",
        "in",
        "on",
        "wg0",
        "to",
        "10.8.0.1",
        "port",
        &port,
        "proto",
        "tcp",
        "comment",
        "h07p-vpn-app",
    ]);
    crate::telemetry::command("ufw", &args, 5)
        .ok_or_else(|| "Could not update the WireGuard-only firewall rule".into())
        .map(|_| ())
}
fn read_configs() -> Result<Vec<Config>, String> {
    let file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(config_path())
    {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(_) => return Err("Cannot read VPN configuration".into()),
    };
    if file
        .metadata()
        .map_err(|_| "Cannot inspect VPN configuration")?
        .len()
        > 65536
    {
        return Err("VPN configuration exceeds size limit".into());
    }
    let configs: Vec<Config> = serde_json::from_reader(file.take(65537)).map_err(|_| {
        "Invalid VPN configuration; restore the control-plane backup before changing relays"
    })?;
    if configs.len() > 20 {
        return Err("VPN configuration exceeds relay limit".into());
    }
    let mut ports = std::collections::BTreeSet::new();
    for config in &configs {
        validate(config)?;
        if !ports.insert(config.port) {
            return Err("Duplicate VPN port".into());
        }
    }
    Ok(configs)
}
pub fn restore() {
    let mut relays = manager().lock().unwrap_or_else(|e| e.into_inner());
    let Ok(configs) = read_configs() else { return };
    let targets = host_targets();
    for config in configs {
        if !targets.contains(&config.target) {
            continue;
        }
        if let Ok(relay) = start(
            config.clone(),
            ([10, 8, 0, 1], config.port).into(),
            Some("wg0"),
        ) {
            relays.insert(config.port, relay);
        }
    }
}
fn host_targets() -> Vec<SocketAddr> {
    crate::telemetry::command("ss", &["-H", "-ltn"], 2)
        .map(|s| crate::telemetry::listening_targets(&s).0)
        .unwrap_or_default()
}
pub fn control(op: &str, v: &Value) -> Result<Value, String> {
    let mut relays = manager().lock().unwrap_or_else(|e| e.into_inner());
    let mut configs = read_configs()?;
    match op {
        "vpn_apps_status" => {}
        "vpn_apps_add" => {
            if std::env::var("H07P_RELAYS").as_deref() == Ok("false") {
                return Err("VPN changes are disabled in this fixture".into());
            }
            let config: Config = serde_json::from_value(v["config"].clone())
                .map_err(|_| "Select a detected service and VPN port")?;
            validate(&config)?;
            if configs.len() >= 20 || configs.iter().any(|c| c.port == config.port) {
                return Err("VPN relay limit reached or port already configured".into());
            }
            if !host_targets().contains(&config.target) {
                return Err("The selected service is no longer listening on this host. Detect services again.".into());
            }
            // Do not chain relays into other VPN relays.
            if config.target.ip() == std::net::IpAddr::V4(std::net::Ipv4Addr::new(10, 8, 0, 1)) {
                return Err("Select the original local or LAN listener, not a VPN relay".into());
            }
            let relay = start(
                config.clone(),
                ([10, 8, 0, 1], config.port).into(),
                Some("wg0"),
            )?;
            firewall(config.port, true)?;
            configs.push(config.clone());
            if let Err(error) = save(&configs) {
                let _ = firewall(config.port, false);
                return Err(error);
            }
            relays.insert(config.port, relay);
        }
        "vpn_apps_remove" => {
            if std::env::var("H07P_RELAYS").as_deref() == Ok("false") {
                return Err("VPN changes are disabled in this fixture".into());
            }
            let port = v["port"]
                .as_u64()
                .and_then(|n| u16::try_from(n).ok())
                .ok_or("Select a configured VPN port")?;
            if !configs.iter().any(|c| c.port == port) {
                return Err("VPN relay does not exist".into());
            }
            configs.retain(|c| c.port != port);
            save(&configs)?;
            relays.remove(&port);
            firewall(port, false)?;
        }
        _ => return Err("Unsupported VPN action".into()),
    }
    Ok(
        json!({"relays":configs.iter().map(|c|json!({"name":c.name,"target":c.target.to_string(),"port":c.port,"host":"10.8.0.1","authentication":"unchanged","listening":relays.contains_key(&c.port)})).collect::<Vec<_>>(),"interface":"wg0","host":"10.8.0.1","wireguard_present":std::path::Path::new("/sys/class/net/wg0").exists()}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn relay_removal_closes_listener_and_active_connections_without_changing_bytes() {
        let backend = TcpListener::bind("127.0.0.1:0").unwrap();
        let target = backend.local_addr().unwrap();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = backend.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut bytes = [0; 4];
            stream.read_exact(&mut bytes).unwrap();
            assert_eq!(&bytes, b"test");
            stream.write_all(b"okay").unwrap();
            let mut rest = [0];
            assert_eq!(stream.read(&mut rest).unwrap(), 0);
        });
        let free = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = free.local_addr().unwrap();
        drop(free);
        let relay = start(
            Config {
                name: "Fixture".into(),
                target,
                port: address.port(),
            },
            address,
            None,
        )
        .unwrap();
        let mut client = TcpStream::connect(address).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        client.write_all(b"test").unwrap();
        let mut bytes = [0; 4];
        client.read_exact(&mut bytes).unwrap();
        assert_eq!(&bytes, b"okay");
        drop(relay);
        let mut rest = [0];
        assert_eq!(client.read(&mut rest).unwrap(), 0);
        assert!(TcpStream::connect(address).is_err());
        server.join().unwrap();
    }
    #[test]
    fn privileged_and_existing_bridge_ports_are_reserved() {
        for (target, port) in [
            ("127.0.0.1:8080", 22),
            ("127.0.0.1:4097", 9000),
            ("127.0.0.1:8080", 8765),
            ("0.0.0.0:8080", 9000),
        ] {
            assert!(validate(&Config {
                name: "Fixture".into(),
                target: target.parse().unwrap(),
                port
            })
            .is_err());
        }
        assert!(validate(&Config {
            name: "Fixture".into(),
            target: "127.0.0.1:8080".parse().unwrap(),
            port: 18080
        })
        .is_ok());
    }
}
