//! Preserve the installed native web authentication bridge. Credentials stay in
//! trusted service memory, never in URLs, reports, logs or worker launch envs.
use std::{
    io::{self, BufRead, BufReader, Read, Write},
    net::TcpStream,
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
    Some((
        basic(
            &std::env::var("OPENCODE_PUBLIC_USERNAME").ok()?,
            &std::env::var("OPENCODE_PUBLIC_PASSWORD").ok()?,
        )?,
        basic(
            &std::env::var("OPENCODE_BACKEND_USERNAME").ok()?,
            &std::env::var("OPENCODE_BACKEND_PASSWORD").ok()?,
        )?,
    ))
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
fn respond(client: &mut TcpStream, code: &str, extra: &str) {
    let _=write!(client,"HTTP/1.1 {code}\r\n{extra}Cache-Control: no-store\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
}
pub fn serve(
    mut client: TcpStream,
    port: u16,
    expected: &str,
    replacement: Option<&str>,
    handoff: bool,
) {
    let _ = client.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = client.set_write_timeout(Some(Duration::from_secs(180)));
    let mut bytes = Vec::new();
    let mut block = [0; 4096];
    let split = loop {
        if let Some(n) = bytes.windows(4).position(|b| b == b"\r\n\r\n") {
            if n > 16384 {
                respond(&mut client, "431 Request Header Fields Too Large", "");
                return;
            }
            break n;
        }
        if bytes.len() > 16384 {
            respond(&mut client, "431 Request Header Fields Too Large", "");
            return;
        }
        match client.read(&mut block) {
            Ok(0) | Err(_) => return,
            Ok(n) => bytes.extend_from_slice(&block[..n]),
        }
    };
    let Ok(request) = rewrite(&bytes[..split], expected, replacement) else {
        respond(
            &mut client,
            "401 Unauthorized",
            "WWW-Authenticate: Basic realm=\"Playground native web\"\r\n",
        );
        bytes.fill(0);
        return;
    };
    let initial = bytes.split_off(split + 4);
    bytes.fill(0);
    if !request.upgrade && !request.chunked && initial.len() as u64 > request.length {
        respond(&mut client, "400 Bad Request", "");
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
            respond(&mut client, "302 Found", &format!("Location: {token}\r\n"));
        } else {
            respond(&mut client, "503 Service Unavailable", "");
        }
        return;
    }
    let Ok(mut upstream) =
        TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_secs(5))
    else {
        respond(&mut client, "503 Service Unavailable", "");
        return;
    };
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
