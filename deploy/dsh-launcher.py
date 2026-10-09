#!/usr/bin/python3
"""Drop to the DSH account and keep its one-time browser token private."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

STATE = Path("/var/lib/huou07-dsh")
DSH_HOME = STATE / "dsh"
WORKSPACE = Path("/srv/huou07-dsh-workspaces")
APP = Path("/opt/huou07-dsh/app/node_modules/.bin/dsh")
TOKEN_FILE = Path("/run/huou07-dsh-link/url")
TOKEN_RE = re.compile(r"^/\?token=[A-Za-z0-9_-]{32,128}$")


def trusted_host() -> str | None:
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
                    return f"{value}:3080"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def save_url(line: str) -> bool:
    match = re.search(r"dsh web:\s+(https?://\S+)", line)
    if not match:
        return False
    try:
        url = urlsplit(match.group(1))
        if url.scheme != "http" or url.hostname != "127.0.0.1" or url.port != 3080:
            return False
        query = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
        if url.path not in {"", "/"} or url.fragment or len(query) != 1 or query[0][0] != "token":
            return False
        safe_url = f"/?token={query[0][1]}"
        if not TOKEN_RE.fullmatch(safe_url):
            return False
        token_gid = os.stat(TOKEN_FILE.parent).st_gid
        temporary = TOKEN_FILE.with_name(f".url-{os.getpid()}")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, (safe_url + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chown(temporary, 0, token_gid)
        os.chmod(temporary, 0o440)
        os.replace(temporary, TOKEN_FILE)
        return True
    except (OSError, ValueError):
        return False


def main() -> int:
    os.environ.update({
        "HOME": str(STATE),
        "DSH_HOME": str(DSH_HOME),
        "XDG_CONFIG_HOME": str(STATE / "config"),
        "XDG_DATA_HOME": str(STATE / "data"),
        "XDG_STATE_HOME": str(STATE / "state"),
        "XDG_CACHE_HOME": str(STATE / "cache"),
        "PATH": "/opt/huou07-dsh/node/bin:/opt/huou07-dsh/app/node_modules/.bin:/usr/local/libexec/huou07-opencode:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin",
    })
    argv = [
        "/usr/bin/setpriv", "--no-new-privs", "--inh-caps=-all",
        "--ambient-caps=-all", "--reuid=huou07-dsh",
        "--regid=huou07-dsh", "--clear-groups", "--", str(APP),
        "--profile", "web", "--no-open", "--host", "127.0.0.1", "--port", "3080",
    ]
    host = trusted_host()
    if host:
        argv.extend(["--trusted-host", host])
    TOKEN_FILE.unlink(missing_ok=True)
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    assert child.stdout is not None
    try:
        for line in child.stdout:
            if save_url(line):
                print("DSH Web token ready for the private dashboard launcher.", file=sys.stderr, flush=True)
        return child.wait()
    finally:
        TOKEN_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
