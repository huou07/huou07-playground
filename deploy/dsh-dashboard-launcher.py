#!/usr/bin/env python3
"""Run DSH Web and publish its one-time URL to the existing dashboard."""

from __future__ import annotations

import os
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


PORT = 3080
URL_FILE = Path(os.environ.get("DSH_URL_FILE", "/run/huou07-dsh-link/url"))
TOKEN_URL = re.compile(r"^/\?token=[A-Za-z0-9_-]{32,128}$")
DSH = Path.home() / ".local/bin/dsh"


def wg_trusted_host() -> str | None:
    """Trust only the host/port reached through the existing wg0 dashboard relay."""
    try:
        result = subprocess.run(
            ["/usr/sbin/ip", "-j", "-4", "addr", "show", "dev", "wg0"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        for interface in json.loads(result.stdout):
            for address in interface.get("addr_info", []):
                value = address.get("local")
                if address.get("family") == "inet" and isinstance(value, str):
                    return f"{value}:{PORT}"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def save_url(line: str) -> None:
    match = re.search(r"dsh web:\s+(https?://\S+)", line)
    if not match:
        return
    try:
        url = urlsplit(match.group(1))
        query = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
        if url.scheme != "http" or url.hostname != "127.0.0.1" or url.port != PORT:
            return
        if url.path not in {"", "/"} or url.fragment or len(query) != 1 or query[0][0] != "token":
            return
        value = f"/?token={query[0][1]}"
        if not TOKEN_URL.fullmatch(value):
            return
        temp = URL_FILE.with_name(f".url-{os.getpid()}")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
        try:
            # UMask=0077 protects the rest of DSH's runtime files. This one
            # short-lived bearer URL is intentionally group-readable by the
            # existing dashboard service and by no other account.
            os.fchmod(fd, 0o640)
            os.write(fd, (value + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, URL_FILE)
        print("DSH Web login link refreshed for the private dashboard.", file=sys.stderr, flush=True)
    except (OSError, ValueError):
        return


def main() -> int:
    if not DSH.is_file() or not os.access(DSH, os.X_OK):
        print(f"DSH executable is missing: {DSH}", file=sys.stderr)
        return 1
    URL_FILE.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({"HOME": str(Path.home()), "DSH_HOME": str(Path.home() / ".dsh")})
    argv = [str(DSH), "--profile", "web", "--no-open", "--host", "127.0.0.1", "--port", str(PORT)]
    host = wg_trusted_host()
    if host:
        argv.extend(["--trusted-host", host])
    child = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
        env=env,
    )
    assert child.stdout is not None
    try:
        for line in child.stdout:
            save_url(line)
            # Keep startup output useful without journaling its bearer token.
            if "dsh web:" not in line:
                print(line, end="", file=sys.stderr, flush=True)
        return child.wait()
    finally:
        URL_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
