use axum::{
    body::Body,
    extract::{DefaultBodyLimit, Path, Query, Request, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post, put},
    Json, Router,
};
use futures_util::StreamExt;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::UnixStream,
};
use tokio_util::io::ReaderStream;
#[derive(Clone)]
pub struct App {
    pub state: PathBuf,
    failures: Arc<Mutex<Vec<u64>>>,
}
fn fail(status: StatusCode, message: &str) -> Response {
    (status, Json(json!({"error":message}))).into_response()
}
fn hash(value: &str) -> String {
    format!("{:x}", Sha256::digest(value.as_bytes()))
}
fn connection(app: &App) -> Result<Connection, String> {
    Connection::open(app.state.join("owner.db")).map_err(|e| e.to_string())
}
fn cookie(headers: &HeaderMap) -> Option<&str> {
    headers
        .get(header::COOKIE)?
        .to_str()
        .ok()?
        .split(';')
        .find_map(|s| s.trim().strip_prefix("h07p_owner="))
}
fn session(app: &App, headers: &HeaderMap) -> Option<(String, String)> {
    let token = cookie(headers)?;
    if token.len() != 64 {
        return None;
    }
    let c = connection(app).ok()?;
    c.query_row(
        "SELECT username,csrf FROM sessions WHERE token=?1 AND expires>?2",
        params![hash(token), crate::now()],
        |r| Ok((r.get(0)?, r.get(1)?)),
    )
    .optional()
    .ok()?
}
fn origin_ok(headers: &HeaderMap) -> bool {
    let Some(origin) = headers.get(header::ORIGIN) else {
        return true;
    };
    let Ok(origin) = origin.to_str() else {
        return false;
    };
    let host = headers
        .get(header::HOST)
        .and_then(|h| h.to_str().ok())
        .unwrap_or("");
    origin == format!("http://{host}") || origin == format!("https://{host}")
}
#[derive(Clone)]
struct TicketIdentity(Value);
fn file_ticket(app: &App, request: &Request) -> Option<TicketIdentity> {
    if !["/api/fs/download", "/api/fs/preview"].contains(&request.uri().path()) {
        return None;
    }
    let url = match reqwest::Url::parse(&format!("http://localhost{}", request.uri())) {
        Ok(u) => u,
        Err(_) => return None,
    };
    let q = url
        .query_pairs()
        .into_owned()
        .collect::<std::collections::HashMap<_, _>>();
    let token = q.get("ticket").filter(|t| t.len() == 64)?;
    let Ok(c) = connection(app) else { return None };
    c.query_row("SELECT t.identity FROM tickets t JOIN sessions s ON s.token=t.owner WHERE t.token=?1 AND t.expires>?2 AND s.expires>?2 AND t.area=?3 AND t.path=?4 AND t.kind=?5",
        params![hash(token),crate::now(),q.get("area").map_or("nas",String::as_str),q.get("path").map_or("/",String::as_str),request.uri().path().rsplit('/').next().unwrap_or("")],|r|r.get::<_,String>(0)).ok().and_then(|s|serde_json::from_str(&s).ok()).map(TicketIdentity)
}
async fn ticket(State(app): State<App>, headers: HeaderMap, Json(v): Json<Value>) -> Response {
    let (Some(area), Some(path), Some(kind)) =
        (v["area"].as_str(), v["path"].as_str(), v["kind"].as_str())
    else {
        return fail(StatusCode::BAD_REQUEST, "Select a file and ticket kind");
    };
    if !["nas", "storage"].contains(&area) || !["download", "preview"].contains(&kind) {
        return fail(StatusCode::BAD_REQUEST, "Invalid file ticket scope");
    }
    let probe =
        json!({"op":"fs_read","area":area,"path":path,"length":0,"preview":kind=="preview"});
    let identity = match file_stream(&probe).await {
        Ok((meta, _)) => meta,
        Err(error) => return fail(StatusCode::BAD_REQUEST, &error),
    };
    let Ok(token) = crate::random_token() else {
        return fail(
            StatusCode::INTERNAL_SERVER_ERROR,
            "Ticket generation failed",
        );
    };
    let Ok(c) = connection(&app) else {
        return fail(
            StatusCode::INTERNAL_SERVER_ERROR,
            "Ticket store unavailable",
        );
    };
    let _ = c.execute(
        "DELETE FROM tickets WHERE expires<=?1 OR owner NOT IN (SELECT token FROM sessions)",
        [crate::now()],
    );
    let owner = hash(cookie(&headers).unwrap_or(""));
    let count = c
        .query_row(
            "SELECT count(*) FROM tickets WHERE owner=?1",
            [&owner],
            |r| r.get::<_, u64>(0),
        )
        .unwrap_or(1000);
    if count >= 1000 {
        return fail(
            StatusCode::TOO_MANY_REQUESTS,
            "Too many active file links; sign out to revoke them",
        );
    }
    if c.execute(
        "INSERT INTO tickets VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![
            hash(&token),
            owner,
            area,
            path,
            kind,
            crate::now() + 900,
            identity.to_string()
        ],
    )
    .is_err()
    {
        return fail(StatusCode::INTERNAL_SERVER_ERROR, "Ticket storage failed");
    }
    let mut url = reqwest::Url::parse(&format!("http://localhost/api/fs/{kind}")).unwrap();
    url.query_pairs_mut()
        .append_pair("area", area)
        .append_pair("path", path)
        .append_pair("ticket", &token);
    Json(json!({"url":format!("{}?{}",url.path(),url.query().unwrap()),"expires_in":900}))
        .into_response()
}
async fn gate(State(app): State<App>, mut request: Request, next: Next) -> Response {
    let path = request.uri().path();
    if path == "/api/health"
        || path == "/api/owner/session"
        || path == "/api/owner/login"
        || !path.starts_with("/api/")
    {
        return next.run(request).await;
    }
    if request.method() == "GET" {
        if let Some(identity) = file_ticket(&app, &request) {
            request.extensions_mut().insert(identity);
            return next.run(request).await;
        }
    }
    let Some((_, csrf)) = session(&app, request.headers()) else {
        return fail(StatusCode::UNAUTHORIZED, "Owner sign in required");
    };
    if !origin_ok(request.headers())
        || request
            .headers()
            .get("X-H07P-CSRF")
            .and_then(|h| h.to_str().ok())
            != Some(&csrf)
    {
        return fail(StatusCode::FORBIDDEN, "Owner CSRF validation failed");
    }
    next.run(request).await
}
pub async fn rpc(value: &Value) -> Result<Value, String> {
    let socket =
        std::env::var("H07P_HELPER_SOCKET").unwrap_or_else(|_| "/run/h07p/admin.sock".into());
    let mut stream = UnixStream::connect(socket)
        .await
        .map_err(|_| "Protected control helper is unavailable")?;
    stream
        .write_all(format!("{value}\n").as_bytes())
        .await
        .map_err(|_| "Helper request failed")?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    tokio::time::timeout(
        std::time::Duration::from_secs(120),
        reader.read_line(&mut line),
    )
    .await
    .map_err(|_| "Control operation timed out")?
    .map_err(|_| "Control response failed")?;
    let response: Value = serde_json::from_str(&line).map_err(|_| "Invalid control response")?;
    if response["ok"] != true {
        return Err(response["error"]
            .as_str()
            .unwrap_or("Control operation failed")
            .into());
    }
    Ok(response["data"].clone())
}
async fn login(State(app): State<App>, headers: HeaderMap, Json(value): Json<Value>) -> Response {
    if !origin_ok(&headers) {
        return fail(StatusCode::FORBIDDEN, "Sign in from this dashboard");
    }
    let now = crate::now();
    {
        let mut f = app.failures.lock().unwrap_or_else(|e| e.into_inner());
        f.retain(|t| *t + 60 > now);
        if f.len() >= 10 {
            return fail(
                StatusCode::TOO_MANY_REQUESTS,
                "Too many sign-in attempts; retry in one minute",
            );
        }
        f.push(now);
    }
    let request =
        json!({"op":"authenticate","username":value["username"],"password":value["password"]});
    match rpc(&request).await {
        Ok(user) => {
            let token = match crate::random_token() {
                Ok(s) => s,
                Err(_) => {
                    return fail(
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "Session generation failed",
                    )
                }
            };
            let csrf = match crate::random_token() {
                Ok(s) => s,
                Err(_) => {
                    return fail(
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "Session generation failed",
                    )
                }
            };
            let c = match connection(&app) {
                Ok(c) => c,
                Err(_) => {
                    return fail(
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "Session store unavailable",
                    )
                }
            };
            let _ = c.execute("DELETE FROM sessions WHERE expires<=?1", [now]);
            if c.execute(
                "INSERT INTO sessions VALUES(?1,?2,?3,?4)",
                params![
                    hash(&token),
                    user["username"].as_str().unwrap_or("huou07"),
                    csrf,
                    now + 8 * 3600
                ],
            )
            .is_err()
            {
                return fail(StatusCode::INTERNAL_SERVER_ERROR, "Could not save session");
            }
            let mut response =
                Json(json!({"authenticated":true,"username":user["username"],"csrf":csrf}))
                    .into_response();
            response.headers_mut().insert(
                header::SET_COOKIE,
                HeaderValue::from_str(&format!(
                    "h07p_owner={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800{}",
                    if std::env::var("H07P_HTTPS").as_deref() == Ok("true") {
                        "; Secure"
                    } else {
                        ""
                    }
                ))
                .unwrap(),
            );
            response
        }
        Err(_) => fail(StatusCode::UNAUTHORIZED, "Invalid owner credentials"),
    }
}
async fn owner_session(State(app): State<App>, headers: HeaderMap) -> Json<Value> {
    Json(
        match session(&app, &headers).filter(|(_, csrf)| {
            headers.get("X-H07P-CSRF").and_then(|h| h.to_str().ok()) == Some(csrf)
        }) {
            Some((user, csrf)) => json!({"authenticated":true,"username":user,"csrf":csrf}),
            None => json!({"authenticated":false}),
        },
    )
}
async fn logout(State(app): State<App>, headers: HeaderMap) -> Response {
    if let Some(token) = cookie(&headers) {
        if let Ok(c) = connection(&app) {
            let _ = c.execute("DELETE FROM sessions WHERE token=?1", [hash(token)]);
        }
    }
    let mut r = Json(json!({"ok":true})).into_response();
    r.headers_mut().insert(
        header::SET_COOKIE,
        HeaderValue::from_static("h07p_owner=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"),
    );
    r
}
fn rpc_response(result: Result<Value, String>) -> Response {
    match result {
        Ok(value) => Json(value).into_response(),
        Err(error) => fail(
            if error.starts_with("REVISION_CONFLICT") {
                StatusCode::CONFLICT
            } else {
                StatusCode::BAD_REQUEST
            },
            &error,
        ),
    }
}
async fn status() -> Response {
    rpc_response(rpc(&json!({"op":"status"})).await)
}
async fn control(Path(op): Path<String>, Json(mut v): Json<Value>) -> Response {
    if !["dry-run", "apply", "rollback", "approve", "scan"].contains(&op.as_str()) {
        return fail(StatusCode::NOT_FOUND, "Unknown control operation");
    }
    v["op"] = op.into();
    rpc_response(rpc(&v).await)
}
async fn listing(Query(q): Query<std::collections::HashMap<String, String>>) -> Response {
    let v = json!({"op":"fs_list","area":q.get("area").map_or("nas",String::as_str),"path":q.get("path").map_or("/",String::as_str),"offset":q.get("offset").and_then(|s|s.parse::<u64>().ok()).unwrap_or(0)});
    rpc_response(rpc(&v).await)
}
async fn guard_get(Path(op): Path<String>) -> Response {
    if !["status", "events"].contains(&op.as_str()) {
        return fail(StatusCode::NOT_FOUND, "Unknown Guard view");
    }
    rpc_response(rpc(&json!({"op":format!("guard_{op}")})).await)
}
async fn guard_post(Path(op): Path<String>, Json(mut v): Json<Value>) -> Response {
    if !["configure", "ack", "plan", "clean", "restore"].contains(&op.as_str()) {
        return fail(StatusCode::NOT_FOUND, "Unknown Guard operation");
    }
    v["op"] = format!("guard_{op}").into();
    rpc_response(rpc(&v).await)
}
async fn vpn_apps_get() -> Response {
    rpc_response(rpc(&json!({"op":"vpn_apps_status"})).await)
}
async fn app_logins_get() -> Response {
    rpc_response(rpc(&json!({"op":"app_logins_status"})).await)
}
async fn app_logins_post(Json(mut v): Json<Value>) -> Response {
    if v.to_string().len() > 120000 {
        return fail(
            StatusCode::PAYLOAD_TOO_LARGE,
            "Login selection exceeds the request limit. Save fewer entries.",
        );
    }
    v["op"] = "app_logins_save".into();
    rpc_response(rpc(&v).await)
}
async fn vpn_apps_post(Path(op): Path<String>, Json(mut v): Json<Value>) -> Response {
    if !["add", "remove"].contains(&op.as_str()) {
        return fail(StatusCode::NOT_FOUND, "Unknown VPN operation");
    }
    v["op"] = format!("vpn_apps_{op}").into();
    rpc_response(rpc(&v).await)
}
async fn mutate(Json(mut v): Json<Value>) -> Response {
    v["op"] = "fs_mutate".into();
    rpc_response(rpc(&v).await)
}
async fn file_search(Json(mut v): Json<Value>) -> Response {
    v["op"] = "fs_search".into();
    rpc_response(rpc(&v).await)
}
async fn file_stream(v: &Value) -> Result<(Value, BufReader<UnixStream>), String> {
    let socket =
        std::env::var("H07P_HELPER_SOCKET").unwrap_or_else(|_| "/run/h07p/admin.sock".into());
    let mut s = UnixStream::connect(socket)
        .await
        .map_err(|_| "File adapter unavailable")?;
    s.write_all(format!("{v}\n").as_bytes())
        .await
        .map_err(|_| "File request failed")?;
    let mut reader = BufReader::new(s);
    let mut line = String::new();
    reader
        .read_line(&mut line)
        .await
        .map_err(|_| "File metadata failed")?;
    let meta: Value = serde_json::from_str(&line).map_err(|_| "File unavailable")?;
    if meta["ok"] != true {
        return Err(meta["error"].as_str().unwrap_or("File unavailable").into());
    }
    Ok((meta["data"].clone(), reader))
}
async fn download(
    Path(kind): Path<String>,
    Query(q): Query<std::collections::HashMap<String, String>>,
    headers: HeaderMap,
    ticket: Option<axum::extract::Extension<TicketIdentity>>,
) -> Response {
    if kind != "download" && kind != "preview" {
        return fail(StatusCode::NOT_FOUND, "Unknown file operation");
    }
    let mut v = json!({"op":"fs_read","area":q.get("area").map_or("nas",String::as_str),"path":q.get("path").map_or("/",String::as_str),"preview":kind=="preview"});
    if let Some(axum::extract::Extension(TicketIdentity(meta))) = ticket {
        for key in [
            "expected_dev",
            "expected_ino",
            "expected_ctime",
            "expected_ctime_nsec",
        ] {
            v[key] = meta[key].clone();
        }
    }
    let mut partial = false;
    if let Some(range) = headers.get(header::RANGE).and_then(|r| r.to_str().ok()) {
        let mut probe = v.clone();
        probe["length"] = 0.into();
        let size = match file_stream(&probe).await {
            Ok((m, _)) => m["size"].as_u64().unwrap_or(0),
            Err(e) => return fail(StatusCode::BAD_REQUEST, &e),
        };
        match parse_range(range, size) {
            Some((a, b)) => {
                v["start"] = a.into();
                v["length"] = (b - a + 1).into();
                partial = true
            }
            None => {
                return fail(
                    StatusCode::RANGE_NOT_SATISFIABLE,
                    "Invalid or multiple byte ranges",
                )
            }
        }
    }
    match file_stream(&v).await {
        Ok((meta, reader)) => {
            let length = meta["length"].as_u64().unwrap_or(0);
            let content = meta["content_type"]
                .as_str()
                .unwrap_or("application/octet-stream");
            let filename = meta["filename"]
                .as_str()
                .unwrap_or("download")
                .chars()
                .map(|c| {
                    if c.is_ascii_alphanumeric() || "._-".contains(c) {
                        c
                    } else {
                        '_'
                    }
                })
                .collect::<String>();
            let mut r = Response::builder()
                .status(if partial { 206 } else { 200 })
                .header(header::CONTENT_TYPE, content)
                .header(header::CONTENT_LENGTH, length.to_string())
                .header(header::ACCEPT_RANGES, "bytes")
                .header(header::CACHE_CONTROL, "no-store")
                .header(
                    header::CONTENT_SECURITY_POLICY,
                    "default-src 'none'; sandbox",
                )
                .header(
                    header::CONTENT_DISPOSITION,
                    format!(
                        "{}; filename=\"{filename}\"",
                        if kind == "preview" {
                            "inline"
                        } else {
                            "attachment"
                        }
                    ),
                );
            if meta["truncated"] == true {
                r = r.header("X-H07P-Truncated", "true");
            }
            if partial {
                let start = meta["start"].as_u64().unwrap_or(0);
                r = r.header(
                    header::CONTENT_RANGE,
                    format!(
                        "bytes {start}-{}/{}",
                        start + length.saturating_sub(1),
                        meta["size"].as_u64().unwrap_or(0)
                    ),
                );
            }
            r.body(Body::from_stream(ReaderStream::new(reader)))
                .unwrap()
        }
        Err(e) => fail(StatusCode::BAD_REQUEST, &e),
    }
}
fn parse_range(range: &str, size: u64) -> Option<(u64, u64)> {
    let (s, e) = range.strip_prefix("bytes=")?.split_once('-')?;
    if size == 0 || e.contains(',') {
        return None;
    }
    let start = if s.is_empty() {
        size.saturating_sub(e.parse::<u64>().ok()?)
    } else {
        s.parse().ok()?
    };
    let end = if e.is_empty() || s.is_empty() {
        size - 1
    } else {
        e.parse::<u64>().ok()?.min(size - 1)
    };
    if start > end || start >= size {
        None
    } else {
        Some((start, end))
    }
}
async fn upload(
    Query(q): Query<std::collections::HashMap<String, String>>,
    request: Request,
) -> Response {
    let Some(length) = request
        .headers()
        .get(header::CONTENT_LENGTH)
        .and_then(|h| h.to_str().ok())
        .and_then(|s| s.parse::<u64>().ok())
    else {
        return fail(StatusCode::LENGTH_REQUIRED, "Content-Length is required");
    };
    if length > 512 * 1024 * 1024 {
        return fail(StatusCode::PAYLOAD_TOO_LARGE, "Upload limit is 512 MiB");
    }
    let socket =
        std::env::var("H07P_HELPER_SOCKET").unwrap_or_else(|_| "/run/h07p/admin.sock".into());
    let mut s = match UnixStream::connect(socket).await {
        Ok(s) => s,
        Err(_) => return fail(StatusCode::SERVICE_UNAVAILABLE, "File adapter unavailable"),
    };
    let v = json!({"op":"fs_upload","area":q.get("area").map_or("nas",String::as_str),"path":q.get("path").map_or("/",String::as_str),"length":length});
    if s.write_all(format!("{v}\n").as_bytes()).await.is_err() {
        return fail(StatusCode::BAD_GATEWAY, "Upload adapter failed");
    }
    let mut body = request.into_body().into_data_stream();
    while let Some(data) = body.next().await {
        match data {
            Ok(data) => {
                if s.write_all(&data).await.is_err() {
                    return fail(
                        StatusCode::BAD_REQUEST,
                        "Upload failed; no completed file was published",
                    );
                }
            }
            Err(_) => return fail(StatusCode::BAD_REQUEST, "Upload canceled"),
        }
    }
    let mut line = String::new();
    if BufReader::new(s).read_line(&mut line).await.is_err() {
        return fail(StatusCode::BAD_REQUEST, "Upload interrupted");
    }
    let response: Value =
        serde_json::from_str(&line).unwrap_or(json!({"ok":false,"error":"Upload failed"}));
    if response["ok"] == true {
        (StatusCode::CREATED, Json(response["data"].clone())).into_response()
    } else {
        fail(
            StatusCode::BAD_REQUEST,
            response["error"].as_str().unwrap_or("Upload failed"),
        )
    }
}
pub fn app(static_root: PathBuf) -> Result<Router, String> {
    let state = std::env::var_os("H07P_STATE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| "/var/lib/huou07-playground".into());
    std::fs::create_dir_all(&state).map_err(|e| e.to_string())?;
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&state, std::fs::Permissions::from_mode(0o700))
            .map_err(|e| e.to_string())?;
    }
    let app = App {
        state,
        failures: Arc::new(Mutex::new(Vec::new())),
    };
    connection(&app)?.execute_batch("CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,username TEXT,csrf TEXT,expires INTEGER);CREATE TABLE IF NOT EXISTS tickets(token TEXT PRIMARY KEY,owner TEXT NOT NULL,area TEXT NOT NULL,path TEXT NOT NULL,kind TEXT NOT NULL,expires INTEGER NOT NULL,identity TEXT NOT NULL);").map_err(|e|e.to_string())?;
    let router = Router::new()
        .route("/api/health", get(|| async { Json(json!({"ok":true})) }))
        .route("/api/owner/login", post(login))
        .route("/api/owner/session", get(owner_session))
        .route("/api/owner/logout", post(logout))
        .route("/api/control/status", get(status))
        .route("/api/setup/vpn/apps", get(vpn_apps_get))
        .route(
            "/api/setup/logins",
            get(app_logins_get).post(app_logins_post),
        )
        .route("/api/setup/vpn/apps/{op}", post(vpn_apps_post))
        .route("/api/control/{op}", post(control))
        .route(
            "/api/security/credential-guard/{op}",
            get(guard_get).post(guard_post),
        )
        .route("/api/fs/list", get(listing))
        .route("/api/fs/search", post(file_search))
        .route("/api/fs/mutate", post(mutate))
        .route("/api/fs/ticket", post(ticket))
        .route(
            "/api/fs/upload",
            put(upload).layer(DefaultBodyLimit::disable()),
        )
        .route("/api/fs/{kind}", get(download))
        .with_state(app.clone())
        .merge(crate::telemetry::router())
        .fallback_service(
            tower_http::services::ServeDir::new(static_root).append_index_html_on_directories(true),
        )
        .layer(middleware::from_fn_with_state(app, gate))
        .layer(middleware::from_fn(security));
    Ok(router)
}
async fn security(request: Request, next: Next) -> Response {
    let mut r = next.run(request).await;
    r.headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    r.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    r.headers_mut().insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("no-referrer"),
    );
    if !r.headers().contains_key(header::CONTENT_SECURITY_POLICY) {
        r.headers_mut().insert(header::CONTENT_SECURITY_POLICY,HeaderValue::from_static("default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"));
    }
    r
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn valid_single_ranges() {
        assert_eq!(parse_range("bytes=1-4", 10), Some((1, 4)));
        assert_eq!(parse_range("bytes=-3", 10), Some((7, 9)));
        assert_eq!(parse_range("bytes=10-", 10), None);
        assert_eq!(parse_range("bytes=0-1,3-4", 10), None);
    }
    #[test]
    fn rejects_foreign_origin() {
        let mut h = HeaderMap::new();
        h.insert(header::HOST, HeaderValue::from_static("10.8.0.1:8765"));
        h.insert(
            header::ORIGIN,
            HeaderValue::from_static("http://evil.invalid"),
        );
        assert!(!origin_ok(&h));
    }
}
