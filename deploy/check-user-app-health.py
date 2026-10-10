#!/usr/bin/env python3
"""Wait for local playground app health without invoking any model."""

from __future__ import annotations

import argparse
import base64
import http.cookiejar
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import (  # noqa: S310 - fixed local health endpoints
    HTTPCookieProcessor,
    Request,
    build_opener,
    urlopen,
)


def read_env(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            result[key] = value
    return result


def dsh_login_page_ready(base_url: str, token_file: Path) -> bool:
    try:
        token_path = token_file.read_text().strip()
    except OSError:
        return False
    if not re.fullmatch(r"/\?token=[A-Za-z0-9_-]{32,128}", token_path):
        return False
    cookies = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    try:
        with opener.open(base_url.rstrip("/") + token_path, timeout=2) as response:
            return response.status == 200
    except (OSError, HTTPError, URLError, TimeoutError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode-env", type=Path, required=True)
    parser.add_argument("--dsh-token-file", type=Path, default=Path("/run/huou07-dsh-link/url"))
    parser.add_argument("--dsh-url", default="http://127.0.0.1:3080")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8765/api/health")
    parser.add_argument("--opencode-url", default="http://127.0.0.1:4096/global/health")
    parser.add_argument("--litellm-url", default="http://127.0.0.1:4000/health/readiness")
    parser.add_argument("--omniroute-url", default="http://127.0.0.1:20128/healthz")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()

    env = read_env(args.opencode_env)
    auth_value = base64.b64encode(
        (env["OPENCODE_SERVER_USERNAME"] + ":" + env["OPENCODE_SERVER_PASSWORD"]).encode()
    ).decode()
    checks = {
        "dashboard": (args.dashboard_url, None),
        "OpenCode Web": (args.opencode_url, "Basic " + auth_value),
        "LiteLLM": (args.litellm_url, None),
        "OmniRoute": (args.omniroute_url, None),
    }
    pending = set(checks)
    dsh_pending = True
    deadline = time.monotonic() + args.timeout
    while (pending or dsh_pending) and time.monotonic() < deadline:
        for name in tuple(pending):
            url, auth = checks[name]
            try:
                request = Request(url)
                if auth:
                    request.add_header("Authorization", auth)
                with urlopen(request, timeout=2) as response:
                    if response.status == 200:
                        pending.remove(name)
                        print(name + " HTTP health passed.")
            except (OSError, HTTPError, URLError, TimeoutError):
                pass
        if dsh_pending and dsh_login_page_ready(args.dsh_url, args.dsh_token_file):
            dsh_pending = False
            print("DSH Web login page passed.")
        if pending or dsh_pending:
            time.sleep(args.interval)

    if pending or dsh_pending:
        failed = sorted(pending)
        if dsh_pending:
            failed.append("DSH Web")
        print("Application health did not become ready: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
