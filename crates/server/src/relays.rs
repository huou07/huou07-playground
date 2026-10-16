//! VPN-only relays; the HTTP server itself stays unprivileged on loopback.
use std::{
    io,
    net::{TcpListener, TcpStream},
    os::fd::AsRawFd,
    time::Duration,
};
pub fn run() {
    let config = std::env::var("H07P_PRIVATE_SERVICES")
        .unwrap_or_else(|_| "/etc/huou07-playground/private-services.json".into());
    let bytes = std::fs::read(config)
        .unwrap_or_else(|_| include_bytes!("../../../deploy/private-services.json").to_vec());
    let value: serde_json::Value = match serde_json::from_slice(&bytes) {
        Ok(v) => v,
        Err(_) => return,
    };
    let auth = crate::native_proxy::credentials();
    let local = std::env::var("OPENCODE_LOCAL_FORWARD_PORT")
        .ok()
        .and_then(|p| p.parse::<u16>().ok())
        .filter(|p| *p >= 1024)
        .unwrap_or(4096);
    native_listener("127.0.0.1".into(), local, 4097, None, auth.clone(), false);
    if let Ok(interface) = std::env::var("LAN_DSH_INTERFACE") {
        if !interface.is_empty()
            && interface.len() <= 15
            && interface
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
        {
            if let Ok(output) = std::process::Command::new("/usr/sbin/ip")
                .args(["-j", "-4", "address", "show", "dev", &interface])
                .output()
            {
                if let Ok(rows) = serde_json::from_slice::<serde_json::Value>(&output.stdout) {
                    for address in rows
                        .as_array()
                        .into_iter()
                        .flatten()
                        .flat_map(|r| r["addr_info"].as_array().into_iter().flatten())
                        .filter_map(|r| r["local"].as_str())
                        .take(16)
                    {
                        if address.parse::<std::net::Ipv4Addr>().is_ok() {
                            native_listener(
                                address.into(),
                                14096,
                                4097,
                                Some(interface.clone()),
                                auth.clone(),
                                false,
                            );
                            native_listener(
                                address.into(),
                                3080,
                                3080,
                                Some(interface.clone()),
                                auth.clone(),
                                true,
                            );
                        }
                    }
                }
            }
        }
    }
    for service in value["services"].as_array().into_iter().flatten() {
        let Some(port) = service["wireguard_port"].as_u64() else {
            continue;
        };
        let Some(backend) = service["backend_port"].as_u64() else {
            continue;
        };
        if service["id"] == "opencode-web" {
            native_listener(
                "10.8.0.1".into(),
                port as u16,
                4097,
                Some("wg0".into()),
                auth.clone(),
                false,
            );
            continue;
        }
        std::thread::spawn(move || loop {
            match TcpListener::bind(("10.8.0.1", port as u16)) {
                Ok(listener) => {
                    let iface = b"wg0\0";
                    if unsafe {
                        libc::setsockopt(
                            listener.as_raw_fd(),
                            libc::SOL_SOCKET,
                            libc::SO_BINDTODEVICE,
                            iface.as_ptr() as *const _,
                            iface.len() as _,
                        )
                    } != 0
                    {
                        std::thread::sleep(Duration::from_secs(2));
                        continue;
                    }
                    for client in listener.incoming().flatten() {
                        crate::bounded_spawn(move || {
                            if let Ok(target) = TcpStream::connect_timeout(
                                &format!("127.0.0.1:{backend}").parse().unwrap(),
                                Duration::from_secs(5),
                            ) {
                                let _ = target.set_write_timeout(Some(Duration::from_secs(180)));
                                let _ = client.set_write_timeout(Some(Duration::from_secs(180)));
                                let _ = target.set_read_timeout(Some(Duration::from_secs(180)));
                                let _ = client.set_read_timeout(Some(Duration::from_secs(180)));
                                if let (Ok(mut a), Ok(mut b)) =
                                    (client.try_clone(), target.try_clone())
                                {
                                    std::thread::spawn(move || {
                                        let _ = io::copy(&mut a, &mut b);
                                        let _ = b.shutdown(std::net::Shutdown::Write);
                                    });
                                    let (mut client, mut target) = (client, target);
                                    let _ = io::copy(&mut target, &mut client);
                                    let _ = client.shutdown(std::net::Shutdown::Write);
                                }
                            }
                        });
                    }
                }
                Err(_) => std::thread::sleep(Duration::from_secs(2)),
            }
        });
    }
}

fn native_listener(
    address: String,
    port: u16,
    backend: u16,
    interface: Option<String>,
    auth: Option<(String, String)>,
    handoff: bool,
) {
    std::thread::spawn(move || loop {
        if let Ok(listener) = TcpListener::bind((address.as_str(), port)) {
            if let Some(ref device) = interface {
                let Ok(device) = std::ffi::CString::new(device.as_str()) else {
                    return;
                };
                if unsafe {
                    libc::setsockopt(
                        listener.as_raw_fd(),
                        libc::SOL_SOCKET,
                        libc::SO_BINDTODEVICE,
                        device.as_ptr() as *const _,
                        device.as_bytes_with_nul().len() as _,
                    )
                } != 0
                {
                    std::thread::sleep(Duration::from_secs(2));
                    continue;
                }
            }
            for stream in listener.incoming().flatten() {
                let auth = auth.clone();
                crate::bounded_spawn(move || {
                    let (public, private) = auth.unwrap_or_default();
                    // Missing trusted configuration always rejects authentication.
                    crate::native_proxy::serve(
                        stream,
                        backend,
                        &public,
                        if handoff {
                            None
                        } else {
                            Some(private.as_str())
                        },
                        handoff,
                    );
                });
            }
        }
        std::thread::sleep(Duration::from_secs(2));
    });
}
