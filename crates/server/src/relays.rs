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
    for service in value["services"].as_array().into_iter().flatten() {
        let Some(port) = service["wireguard_port"].as_u64() else {
            continue;
        };
        let Some(backend) = service["backend_port"].as_u64() else {
            continue;
        };
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
