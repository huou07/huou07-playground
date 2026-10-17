//! Preserve the installed native web authentication bridge. Credentials stay in
//! trusted service memory, never in URLs, reports, logs or worker launch envs.
use std::{
    collections::BTreeMap,
    fs::OpenOptions,
    io::{self, BufRead, BufReader, Read, Write},
    net::{Shutdown, TcpStream},
    os::unix::fs::OpenOptionsExt,
    sync::{Mutex, OnceLock},
    time::Duration,
};

pub fn basic(user: &str, password: &str) -> Option<String> {
    if user.is_empty() || password.is_empty() || user.contains(':') {
        return None;
    }
    reqwest::blocking::Client::new()
        .get("http://127.0.0.1/")
        .basic_auth(user, Some(password))
        .build()
        .ok()?
        .headers()
        .get("authorization")?
        .to_str()
        .ok()
        .map(str::to_owned)
}
pub fn credentials() -> Option<(String, String)> {
    let (user, password) = public_login()?;
    Some((
        basic(&user, &password)?,
        basic(
            &std::env::var("OPENCODE_BACKEND_USERNAME").ok()?,
            &std::env::var("OPENCODE_BACKEND_PASSWORD").ok()?,
        )?,
    ))
}
pub(crate) fn public_login() -> Option<(String, String)> {
    // Never enable a new auth layer when the original bridge has no login.
    let initial = (
        std::env::var("OPENCODE_PUBLIC_USERNAME").ok()?,
        std::env::var("OPENCODE_PUBLIC_PASSWORD").ok()?,
    );
    basic(&initial.0, &initial.1)?;
    match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(crate::helper::dir().join("public-web-login.json"))
    {
        Ok(file) => {
            if file.metadata().ok()?.len() > 8192 {
                return None;
            }
            let value: serde_json::Value = serde_json::from_reader(file.take(8193)).ok()?;
            let login = (
                value["username"].as_str()?.to_owned(),
                value["password"].as_str()?.to_owned(),
            );
            basic(&login.0, &login.1)?;
            Some(login)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Some(initial),
        Err(_) => None,
    }
}
struct Active {
    client: TcpStream,
    backend: Option<TcpStream>,
}
struct Live {
    auth: Option<(String, String)>,
    generation: u64,
    next: u64,
    active: BTreeMap<u64, Active>,
}
fn disconnect(state: &mut Live) {
    state.generation = state.generation.wrapping_add(1);
    for connection in state.active.values() {
        let _ = connection.client.shutdown(Shutdown::Both);
        if let Some(backend) = &connection.backend {
            let _ = backend.shutdown(Shutdown::Both);
        }
    }
    state.active.clear();
}
fn live() -> &'static Mutex<Live> {
    static AUTH: OnceLock<Mutex<Live>> = OnceLock::new();
    AUTH.get_or_init(|| {
        Mutex::new(Live {
            auth: credentials(),
            generation: 0,
            next: 0,
            active: BTreeMap::new(),
        })
    })
}
pub(crate) fn change_public_login(username: &str, password: &str) -> Result<(), String> {
    if public_login().is_none() || credentials().is_none() {
        return Err(
            "No supported existing public web login. No authentication will be added.".into(),
        );
    }
    if username.len() > 256
        || username.chars().any(char::is_control)
        || !(12..=256).contains(&password.len())
        || password.chars().any(char::is_control)
    {
        return Err("Use a valid existing username and a password of 12 to 256 bytes without control characters.".into());
    }
    let public = basic(username, password).ok_or("Invalid public login")?;
    let mut state = live().lock().unwrap_or_else(|e| e.into_inner());
    let Some((_, backend)) = &state.auth else {
        return Err("Public bridge configuration is unavailable".into());
    };
    let replacement = (public, backend.clone());
    let path = crate::helper::dir().join("public-web-login.json");
    let temporary = path.with_extension(crate::random_token()?);
    let mut bytes =
        serde_json::to_vec(&serde_json::json!({"username":username,"password":password}))
            .map_err(|_| "Login encoding failed")?;
    let mut renamed = false;
    let result = (|| -> io::Result<()> {
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&temporary)?;
        output.write_all(&bytes)?;
        output.sync_all()?;
        std::fs::rename(&temporary, &path)?;
        renamed = true;
        std::fs::File::open(crate::helper::dir())?.sync_all()
    })();
    bytes.fill(0);
    if result.is_err() {
        let _ = std::fs::remove_file(temporary);
        if renamed {
            state.auth = None;
            disconnect(&mut state);
            return Err("Login persistence is uncertain. The bridge was disabled; repair storage and restart the H07P helper before retrying.".into());
        }
        return Err("Could not save the public web login".into());
    }
    state.auth = Some(replacement);
    disconnect(&mut state);
    Ok(())
}
pub(crate) fn managed_serve(client: TcpStream, port: u16, handoff: bool) {
    let (id, generation, auth) = {
        let mut state = live().lock().unwrap_or_else(|e| e.into_inner());
        let Ok(copy) = client.try_clone() else { return };
        state.next = state.next.wrapping_add(1);
        let id = state.next;
        state.active.insert(
            id,
            Active {
                client: copy,
                backend: None,
            },
        );
        (id, state.generation, state.auth.clone().unwrap_or_default())
    };
    serve_inner(
        client,
        port,
        &auth.0,
        if handoff { None } else { Some(&auth.1) },
        handoff,
        Some((id, generation)),
    );
    live()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .active
        .remove(&id);
}
fn equal(a: &[u8], b: &[u8]) -> bool {
    let mut difference = a.len() ^ b.len();
    for (i, value) in b.iter().enumerate() {
        difference |= (a.get(i).copied().unwrap_or(0) ^ value) as usize;
    }
    difference == 0
}
struct Request {
    header: Vec<u8>,
    length: u64,
    chunked: bool,
    upgrade: bool,
    landing: bool,
}
fn rewrite(head: &[u8], expected: &str, replacement: Option<&str>) -> Result<Request, ()> {
    if expected.is_empty() {
        return Err(());
    }
    let text = std::str::from_utf8(head).map_err(|_| ())?;
    let mut lines = text.split("\r\n");
    let first = lines.next().ok_or(())?;
    let parts: Vec<_> = first.split_whitespace().collect();
    if parts.len() != 3
        || !parts[1].starts_with('/')
        || parts[1].starts_with("//")
        || parts[2] != "HTTP/1.1"
    {
        return Err(());
    }
    let mut auth = None;
    let mut length = None;
    let mut upgrade = false;
    let mut cookie = false;
    let mut chunked = false;
    let mut output = vec![first.to_owned()];
    for line in lines {
        if line.is_empty() {
            continue;
        }
        if line.starts_with([' ', '\t']) || line.bytes().any(|b| b < 32 && b != b'\t') {
            return Err(());
        }
        let (name, value) = line.split_once(':').ok_or(())?;
        if name.is_empty() || !name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') {
            return Err(());
        }
        let value = value.trim();
        match name.to_ascii_lowercase().as_str() {
            "authorization" => {
                if auth.replace(value).is_some() {
                    return Err(());
                }
            }
            "proxy-authorization" | "proxy-connection" | "connection" => {}
            "transfer-encoding" => {
                if chunked || !value.eq_ignore_ascii_case("chunked") {
                    return Err(());
                }
                chunked = true;
                output.push("Transfer-Encoding: chunked".into());
            }
            "trailer" => {}
            "content-length" => {
                if length.is_some() {
                    return Err(());
                }
                let size = value.parse::<u64>().map_err(|_| ())?;
                if size > 512 * 1024 * 1024 {
                    return Err(());
                }
                length = Some(size);
                output.push(line.into());
            }
            "upgrade" => {
                if !value.eq_ignore_ascii_case("websocket") {
                    return Err(());
                }
                upgrade = true;
                output.push(line.into());
            }
            "cookie" => {
                let cookies: Vec<_> = value
                    .split(';')
                    .map(str::trim)
                    .filter(|c| c.split_once('=').is_none_or(|(k, _)| k != "h07p_owner"))
                    .collect();
                cookie |= !cookies.is_empty();
                if !cookies.is_empty() {
                    output.push(format!("Cookie: {}", cookies.join("; ")));
                }
            }
            _ => output.push(line.into()),
        }
    }
    if ((chunked && length.is_some()) || (upgrade && (chunked || length.unwrap_or(0) > 0)))
        || !auth.is_some_and(|a| equal(a.as_bytes(), expected.as_bytes()))
    {
        return Err(());
    }
    if let Some(value) = replacement {
        output.push(format!("Authorization: {value}"));
    }
    output.push(
        if upgrade {
            "Connection: Upgrade"
        } else {
            "Connection: close"
        }
        .into(),
    );
    Ok(Request {
        header: format!("{}\r\n\r\n", output.join("\r\n")).into_bytes(),
        length: length.unwrap_or(0),
        chunked,
        upgrade,
        landing: parts[0] == "GET" && parts[1] == "/" && !cookie,
    })
}
fn chunks(input: impl Read, output: &mut impl Write) -> io::Result<()> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidData, "Invalid native request framing");
    let mut input = BufReader::new(input);
    let mut total = 0u64;
    loop {
        let mut line = Vec::new();
        (&mut input).take(129).read_until(b'\n', &mut line)?;
        if !line.ends_with(b"\r\n") || line.len() > 128 {
            return Err(invalid());
        }
        let text = std::str::from_utf8(&line[..line.len() - 2]).map_err(|_| invalid())?;
        let size = text.split(';').next().ok_or_else(invalid)?;
        if size.is_empty() || size.len() > 16 || !size.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(invalid());
        }
        let size = u64::from_str_radix(size, 16).map_err(|_| invalid())?;
        total = total
            .checked_add(size)
            .filter(|n| *n <= 512 * 1024 * 1024)
            .ok_or_else(invalid)?;
        if size == 0 {
            // Drop trailers, particularly credentials; the next HTTP request is
            // never forwarded on this one-request connection.
            let mut budget = 4096;
            loop {
                let mut trailer = Vec::new();
                (&mut input).take(budget).read_until(b'\n', &mut trailer)?;
                if !trailer.ends_with(b"\r\n") || trailer.len() as u64 > budget {
                    return Err(invalid());
                }
                budget -= trailer.len() as u64;
                if trailer == b"\r\n" {
                    break;
                }
                if budget == 0 {
                    return Err(invalid());
                }
            }
            return output.write_all(b"0\r\n\r\n");
        }
        write!(output, "{size:x}\r\n")?;
        if io::copy(&mut (&mut input).take(size), output)? != size {
            return Err(invalid());
        }
        let mut end = [0; 2];
        input.read_exact(&mut end)?;
        if end != *b"\r\n" {
            return Err(invalid());
        }
        output.write_all(&end)?;
    }
}
fn local_authority(authority: &str) -> bool {
    if authority.is_empty()
        || !authority
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b".-:[]".contains(&b))
    {
        return false;
    }
    let (host, port) = if let Some(ipv6) = authority.strip_prefix('[') {
        let Some((address, suffix)) = ipv6.split_once(']') else {
            return false;
        };
        let port = if suffix.is_empty() {
            None
        } else {
            let Some(port) = suffix.strip_prefix(':').and_then(|p| p.parse::<u16>().ok()) else {
                return false;
            };
            Some(port)
        };
        let Ok(address) = address.parse::<std::net::Ipv6Addr>() else {
            return false;
        };
        return port.is_none_or(|port| port != 0)
            && (address.is_loopback() || address.is_unique_local());
    } else if let Some((host, port)) = authority.rsplit_once(':') {
        if host.contains(':') {
            return false;
        }
        let Ok(port) = port.parse::<u16>() else {
            return false;
        };
        (host, Some(port))
    } else {
        (authority, None)
    };
    let local_host = host.eq_ignore_ascii_case("localhost")
        || host.to_ascii_lowercase().ends_with(".localhost")
        || host
            .parse::<std::net::Ipv4Addr>()
            .ok()
            .is_some_and(|ip| ip.is_loopback() || ip.is_private() || ip.is_link_local());
    local_host && port.is_none_or(|port| port != 0)
}

fn same_origin(head: &[u8]) -> Option<String> {
    let text = std::str::from_utf8(head).ok()?;
    let mut host = None;
    let mut origin = None;
    for line in text.split("\r\n").skip(1) {
        if line.is_empty() {
            break;
        }
        if line.starts_with([' ', '\t']) || line.bytes().any(|b| b < 32 && b != b'\t') {
            return None;
        }
        let (name, value) = line.split_once(':')?;
        if name.is_empty() || !name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') {
            return None;
        }
        let value = value.trim();
        match name.to_ascii_lowercase().as_str() {
            "host" => {
                if host.replace(value.to_owned()).is_some() {
                    return None;
                }
            }
            "origin" => {
                if origin.replace(value.to_owned()).is_some() {
                    return None;
                }
            }
            _ => {}
        }
    }
    let host = host?;
    let origin = origin?;
    let (scheme, authority) = origin.split_once("://")?;
    if !matches!(scheme, "http" | "https") || authority != host || !local_authority(authority) {
        return None;
    }
    Some(origin)
}

fn error_response(code: &str, extra: &str, cors_origin: Option<&str>) -> String {
    let cors = cors_origin
        .map(|origin| format!("Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\n"))
        .unwrap_or_default();
    format!("HTTP/1.1 {code}\r\n{extra}{cors}Cache-Control: no-store\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
}

fn respond(client: &mut TcpStream, code: &str, extra: &str, cors_origin: Option<&str>) {
    let _ = client.write_all(error_response(code, extra, cors_origin).as_bytes());
}
#[cfg(test)]
pub fn serve(
    client: TcpStream,
    port: u16,
    expected: &str,
    replacement: Option<&str>,
    handoff: bool,
) {
    serve_inner(client, port, expected, replacement, handoff, None);
}
fn serve_inner(
    mut client: TcpStream,
    port: u16,
    expected: &str,
    replacement: Option<&str>,
    handoff: bool,
    managed: Option<(u64, u64)>,
) {
    let _ = client.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = client.set_write_timeout(Some(Duration::from_secs(180)));
    let mut bytes = Vec::new();
    let mut block = [0; 4096];
    let split = loop {
        if let Some(n) = bytes.windows(4).position(|b| b == b"\r\n\r\n") {
            if n > 16384 {
                respond(&mut client, "431 Request Header Fields Too Large", "", None);
                return;
            }
            break n;
        }
        if bytes.len() > 16384 {
            respond(&mut client, "431 Request Header Fields Too Large", "", None);
            return;
        }
        match client.read(&mut block) {
            Ok(0) | Err(_) => return,
            Ok(n) => bytes.extend_from_slice(&block[..n]),
        }
    };
    let Ok(request) = rewrite(&bytes[..split], expected, replacement) else {
        // Module scripts use CORS mode; expose only same-origin auth challenges
        // so the browser can complete the Basic-auth retry through this bridge.
        let cors_origin = same_origin(&bytes[..split]);
        respond(
            &mut client,
            "401 Unauthorized",
            "WWW-Authenticate: Basic realm=\"Playground native web\"\r\n",
            cors_origin.as_deref(),
        );
        bytes.fill(0);
        return;
    };
    let initial = bytes.split_off(split + 4);
    bytes.fill(0);
    if !request.upgrade && !request.chunked && initial.len() as u64 > request.length {
        respond(&mut client, "400 Bad Request", "", None);
        return;
    }
    if handoff && request.landing {
        let token = std::fs::read_to_string("/run/huou07-dsh-link/url").unwrap_or_default();
        let token = token.trim();
        if token.strip_prefix("/?token=").is_some_and(|s| {
            (32..=128).contains(&s.len())
                && s.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
        }) {
            respond(
                &mut client,
                "302 Found",
                &format!("Location: {token}\r\n"),
                None,
            );
        } else {
            respond(&mut client, "503 Service Unavailable", "", None);
        }
        return;
    }
    let Ok(mut upstream) =
        TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_secs(5))
    else {
        respond(&mut client, "503 Service Unavailable", "", None);
        return;
    };
    if let Some((id, generation)) = managed {
        let mut state = live().lock().unwrap_or_else(|e| e.into_inner());
        if generation != state.generation {
            return;
        }
        let Some(connection) = state.active.get_mut(&id) else {
            return;
        };
        let Ok(copy) = upstream.try_clone() else {
            return;
        };
        connection.backend = Some(copy);
    }
    for stream in [&client, &upstream] {
        let _ = stream.set_read_timeout(Some(Duration::from_secs(180)));
        let _ = stream.set_write_timeout(Some(Duration::from_secs(180)));
    }
    if upstream.write_all(&request.header).is_err() {
        return;
    }
    if request.upgrade {
        if upstream.write_all(&initial).is_err() {
            return;
        }
        if let (Ok(mut a), Ok(mut b)) = (client.try_clone(), upstream.try_clone()) {
            std::thread::spawn(move || {
                let _ = io::copy(&mut a, &mut b);
                let _ = b.shutdown(std::net::Shutdown::Write);
            });
            let _ = io::copy(&mut upstream, &mut client);
            let _ = client.shutdown(std::net::Shutdown::Both);
            let _ = upstream.shutdown(std::net::Shutdown::Both);
        }
    } else {
        if request.chunked {
            if chunks(
                std::io::Cursor::new(initial).chain(&mut client),
                &mut upstream,
            )
            .is_err()
            {
                return;
            }
        } else if upstream.write_all(&initial).is_err()
            || io::copy(
                &mut (&mut client).take(request.length - initial.len() as u64),
                &mut upstream,
            )
            .ok()
                != Some(request.length - initial.len() as u64)
        {
            return;
        }
        let _ = io::copy(&mut upstream, &mut client);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn auth_challenge_cors_is_limited_to_the_exact_origin() {
        assert!(local_authority("127.0.0.1:14096"));
        assert!(local_authority("10.8.0.1:4096"));
        assert!(local_authority("[::1]:14096"));
        assert!(local_authority("app.localhost:8080"));
        assert!(!local_authority("attacker.example:14096"));
        assert!(!local_authority("127.0.0.1:0"));

        let request = b"GET /assets/app.js HTTP/1.1\r\nHost: 127.0.0.1:14096\r\nOrigin: http://127.0.0.1:14096";
        let origin = same_origin(request).unwrap();
        let response = error_response(
            "401 Unauthorized",
            "WWW-Authenticate: Basic realm=\"Playground native web\"\r\n",
            Some(&origin),
        );
        assert!(response.contains("Access-Control-Allow-Origin: http://127.0.0.1:14096\r\n"));
        assert!(response.contains("Vary: Origin\r\n"));
        assert!(response.contains("WWW-Authenticate: Basic realm=\"Playground native web\"\r\n"));

        for request in [
            &b"GET / HTTP/1.1\r\nHost: 127.0.0.1:14096\r\nOrigin: http://attacker.example"[..],
            &b"GET / HTTP/1.1\r\nHost: attacker.example\r\nOrigin: http://attacker.example"[..],
            &b"GET / HTTP/1.1\r\nHost: 127.0.0.1:14096\r\nOrigin: null"[..],
            &b"GET / HTTP/1.1\r\nHost: 127.0.0.1:14096\r\nOrigin: http://127.0.0.1:14096/extra"[..],
            &b"GET / HTTP/1.1\r\nHost: 127.0.0.1:14096\r\nHost: attacker.example\r\nOrigin: http://127.0.0.1:14096"[..],
            &b"GET / HTTP/1.1\r\nHost: 127.0.0.1:14096\r\nOrigin: http://127.0.0.1:14096\r\nOrigin: http://attacker.example"[..],
        ] {
            assert!(same_origin(request).is_none());
        }
        assert!(
            !error_response("401 Unauthorized", "", None).contains("Access-Control-Allow-Origin:")
        );
    }

    #[test]
    fn owner_authentication_is_replaced_not_forwarded() {
        let public = basic("owner", "synthetic-public").unwrap();
        let private = basic("backend", "synthetic-worker").unwrap();
        let req=rewrite(format!("POST /message HTTP/1.1\r\nHost: local\r\nAuthorization: {public}\r\nCookie: h07p_owner=fixture; native_session=ok\r\nContent-Length: 2").as_bytes(),&public,Some(&private)).unwrap();
        let header = String::from_utf8(req.header).unwrap();
        assert!(header.contains(&private));
        assert!(!header.contains(&public));
        assert!(!header.contains("h07p_owner"));
        assert!(header.contains("native_session=ok"));
        assert_eq!(req.length, 2);
        assert!(header.contains("Connection: close"));
    }
    #[test]
    fn forgeries_and_ambiguous_framing_fail_closed() {
        assert!(rewrite(b"GET / HTTP/1.1\r\nAuthorization:", "", None).is_err());
        for header in [
            "Authorization: Basic wrong",
            "Authorization: Basic expected\r\nAuthorization: Basic expected",
            "Authorization: Basic expected\r\nContent-Length: 1\r\nContent-Length: 2",
            "Authorization: Basic expected\r\nTransfer-Encoding: chunked\r\nContent-Length: 1",
            " Authorization: Basic expected",
        ] {
            assert!(rewrite(
                format!("GET / HTTP/1.1\r\n{header}").as_bytes(),
                "Basic expected",
                None
            )
            .is_err());
        }
        let ws = rewrite(
            b"GET /events HTTP/1.1\r\nAuthorization: Basic expected\r\nUpgrade: websocket",
            "Basic expected",
            Some("Basic backend"),
        )
        .unwrap();
        assert!(ws.upgrade);
        assert!(String::from_utf8(ws.header)
            .unwrap()
            .contains("Connection: Upgrade"));
    }
    #[test]
    fn chunked_bodies_are_bounded_and_trailers_cannot_forward_owner_credentials() {
        let mut output = Vec::new();
        chunks(&b"2\r\n{}\r\n0\r\nAuthorization: Basic owner\r\n\r\nGET /next HTTP/1.1\r\nAuthorization: Basic owner\r\n\r\n"[..],&mut output).unwrap();
        assert_eq!(output, b"2\r\n{}\r\n0\r\n\r\n");
        for body in [
            &b"invalid\r\n"[..],
            &b"20000001\r\n"[..],
            &b"3\r\nx"[..],
            &b"1\r\nx!!"[..],
        ] {
            assert!(chunks(body, &mut Vec::new()).is_err());
        }
        assert!(chunks(&vec![b'a'; 4096][..], &mut Vec::new()).is_err());
    }
    #[test]
    fn real_tcp_bridge_preserves_http_streams_and_websocket_upgrade() {
        use std::net::TcpListener;
        for websocket in [false, true] {
            let backend = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let port = backend.local_addr().unwrap().port();
            let proxy = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let address = proxy.local_addr().unwrap();
            let server = std::thread::spawn(move || {
                let (mut stream, _) = backend.accept().unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(3)))
                    .unwrap();
                let mut header = Vec::new();
                let mut byte = [0; 1];
                while !header.ends_with(b"\r\n\r\n") {
                    stream.read_exact(&mut byte).unwrap();
                    header.push(byte[0]);
                }
                let header = String::from_utf8(header).unwrap();
                assert!(header.contains("Authorization: Basic backend"));
                assert!(!header.contains("Basic owner"));
                assert!(!header.contains("h07p_owner"));
                if websocket {
                    stream.write_all(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n").unwrap();
                    let mut payload = [0; 5];
                    stream.read_exact(&mut payload).unwrap();
                    assert_eq!(&payload, b"frame");
                    stream.write_all(b"reply").unwrap();
                } else {
                    assert!(header.contains("Connection: close"));
                    let mut payload = [0; 2];
                    stream.read_exact(&mut payload).unwrap();
                    assert_eq!(&payload, b"{}");
                    stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\ndata: ").unwrap();
                    stream.write_all(b"synthetic\n\n").unwrap();
                }
            });
            let bridge = std::thread::spawn(move || {
                let (stream, _) = proxy.accept().unwrap();
                serve(stream, port, "Basic owner", Some("Basic backend"), false);
            });
            let mut client = TcpStream::connect(address).unwrap();
            client
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let extra = if websocket {
                "Upgrade: websocket\r\n"
            } else {
                "Content-Length: 2\r\n"
            };
            write!(client,"POST /message HTTP/1.1\r\nHost: fixture\r\nAuthorization: Basic owner\r\nCookie: h07p_owner=synthetic\r\n{extra}\r\n{}",if websocket{""}else{"{}"}).unwrap();
            if websocket {
                let mut header = Vec::new();
                let mut byte = [0; 1];
                while !header.ends_with(b"\r\n\r\n") {
                    client.read_exact(&mut byte).unwrap();
                    header.push(byte[0]);
                }
                client.write_all(b"frame").unwrap();
                let mut reply = [0; 5];
                client.read_exact(&mut reply).unwrap();
                assert_eq!(&reply, b"reply");
            } else {
                let mut output = String::new();
                client.read_to_string(&mut output).unwrap();
                assert!(output.ends_with("data: synthetic\n\n"));
            }
            drop(client);
            server.join().unwrap();
            bridge.join().unwrap();
        }
    }
}
