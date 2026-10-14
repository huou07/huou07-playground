use std::{env, net::SocketAddr, path::PathBuf};

use axum::{
    body::Body,
    http::{header, HeaderValue, Request, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use tokio::net::TcpListener;
use tower_http::services::ServeDir;

const CONTENT_SECURITY_POLICY: &str = concat!(
    "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; ",
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
);

async fn health() -> Response {
    let mut response = (StatusCode::OK, "{\"ok\":true}").into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/json; charset=utf-8"),
    );
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    response
}

async fn security_headers(request: Request<Body>, next: Next) -> Response {
    let mut response = next.run(request).await;
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    let is_json = response
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("application/json"));
    if !is_json {
        response.headers_mut().insert(
            header::CONTENT_SECURITY_POLICY,
            HeaderValue::from_static(CONTENT_SECURITY_POLICY),
        );
    }
    response
}

fn static_root() -> PathBuf {
    env::var_os("STATIC_DIR").map(PathBuf::from).unwrap_or_else(|| {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../web/static")
    })
}

fn loopback_addresses(host: &str, port: u16) -> Result<Vec<SocketAddr>, String> {
    if !matches!(host, "127.0.0.1" | "::1" | "localhost") {
        return Err(concat!(
            "Only loopback binding is supported until authentication and private-network ",
            "access controls are implemented.",
        )
        .into());
    }
    if host == "localhost" {
        Ok(vec![
            SocketAddr::from(([127, 0, 0, 1], port)),
            SocketAddr::from((std::net::Ipv6Addr::LOCALHOST, port)),
        ])
    } else {
        host.parse::<std::net::IpAddr>()
            .map(|ip| vec![SocketAddr::new(ip, port)])
            .map_err(|_| "Invalid loopback address.".into())
    }
}

fn app(static_root: PathBuf) -> Router {
    let static_files = ServeDir::new(static_root).append_index_html_on_directories();
    Router::new()
        .route("/api/health", get(health))
        .fallback_service(static_files)
        .layer(middleware::from_fn(security_headers))
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let host = env::var("HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port = env::var("PORT")
        .unwrap_or_else(|_| "8765".into())
        .parse::<u16>()?;
    if port == 0 {
        return Err("PORT must be between 1 and 65535.".into());
    }
    let static_root = static_root();
    if !static_root.is_dir() {
        return Err(format!(
            "Static asset directory is unavailable: {}",
            static_root.display()
        )
        .into());
    }

    let application = app(static_root);
    let mut listeners = Vec::new();
    for address in loopback_addresses(&host, port)? {
        match TcpListener::bind(address).await {
            Ok(listener) => listeners.push(listener),
            Err(error) if host == "localhost" => {
                eprintln!("One localhost address could not be bound: {error}");
            }
            Err(error) => return Err(error.into()),
        }
    }
    if listeners.is_empty() {
        return Err("No loopback listener could be started.".into());
    }

    let tasks = listeners.into_iter().map(|listener| {
        let application = application.clone();
        tokio::spawn(async move { axum::serve(listener, application).await })
    });
    tokio::select! {
        result = async {
            for task in tasks {
                task.await??;
            }
            Ok::<(), Box<dyn std::error::Error>>(())
        } => result?,
        signal = tokio::signal::ctrl_c() => signal?,
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::to_bytes, http::Request};
    use tower::ServiceExt;

    #[tokio::test]
    async fn health_matches_python_reference_payload_and_headers() {
        let response = app(PathBuf::from("web/static"))
            .oneshot(
                Request::builder()
                    .uri("/api/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            "application/json; charset=utf-8"
        );
        assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
        assert_eq!(
            response.headers()[header::X_CONTENT_TYPE_OPTIONS],
            "nosniff"
        );
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], br#"{"ok":true}"#);
    }

    #[tokio::test]
    async fn static_root_serves_the_existing_dashboard_with_security_headers() {
        let response = app(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../web/static"))
            .oneshot(Request::builder().uri("/").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert!(response.headers().contains_key(header::CONTENT_SECURITY_POLICY));
        assert_eq!(
            response.headers()[header::X_CONTENT_TYPE_OPTIONS],
            "nosniff"
        );
        let html = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert!(
            std::str::from_utf8(&html)
                .unwrap()
                .contains("<title>Home · huou07 playground</title>")
        );
    }

    #[tokio::test]
    async fn static_service_does_not_expose_files_outside_its_root() {
        let response = app(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../web/static"))
            .oneshot(
                Request::builder()
                    .uri("/%2e%2e/app.py")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[test]
    fn only_explicit_loopback_hosts_are_accepted() {
        assert!(loopback_addresses("127.0.0.1", 8765).is_ok());
        assert!(loopback_addresses("::1", 8765).is_ok());
        assert!(loopback_addresses("localhost", 8765).is_ok());
        assert!(loopback_addresses("0.0.0.0", 8765).is_err());
    }
}
