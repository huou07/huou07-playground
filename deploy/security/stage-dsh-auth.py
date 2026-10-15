#!/usr/bin/env python3
"""Test installed DSH with a disposable HOME and credential store; no model calls."""
import http.client
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
from pathlib import Path

ENTRY = Path("/home/huou07/.local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js")
PORT = 13080


def request(path, cookie=None):
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    try:
        connection.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        response = connection.getresponse()
        result = response.status, response.getheader("Set-Cookie"), response.read()
        return result
    finally:
        connection.close()


def start(home):
    env = {"HOME": str(home), "DSH_HOME": str(home / ".dsh"), "CODEX_HOME": str(home / ".codex"),
           "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "NO_BROWSER": "1"}
    child = subprocess.Popen(["/usr/local/bin/node", str(ENTRY), "web", "--host", "127.0.0.1",
                              "--port", str(PORT), "--no-open"], cwd=home, env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, close_fds=True)
    lines = queue.Queue()

    def drain():
        for line in child.stdout:
            # Discard all other output: configuration failures may contain private paths.
            match = re.search(rf"dsh web:\s+http://127\.0\.0\.1:{PORT}(/\?token=[A-Za-z0-9_-]{{32,128}})", line)
            if match:
                lines.put(match.group(1))

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    try:
        token_path = lines.get(timeout=45)
    except queue.Empty:
        stop(child)
        raise RuntimeError("Staging DSH did not publish a launch URL; output withheld.") from None
    return child, token_path


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    child.stdout.close()


def main():
    # Check availability without probing or replacing an existing service.
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", PORT))
    checks = {"staging_uid": os.geteuid(), "port": PORT, "live_credentials_copied": False}
    with tempfile.TemporaryDirectory(prefix="dsh-auth-stage-") as directory:
        home = Path(directory)
        child, token = start(home)
        try:
            checks["unauthenticated_index_denied"] = request("/")[0] == 401
            checks["unauthenticated_api_denied"] = request("/api")[0] == 401
            status, cookie, _ = request(token)
            checks["token_mints_session_cookie"] = status == 303 and bool(cookie)
            assert cookie, "staging cookie missing"
            cookie = cookie.split(";", 1)[0]
            checks["authenticated_index_is_html"] = (lambda r: r[0] == 200 and b"<html" in r[2].lower())(request("/", cookie))
            checks["forged_cookie_denied"] = request("/", cookie + "tampered")[0] == 401
            store = home / ".dsh/.credentials.yaml"
            checks["fresh_browser_credential_store_created"] = store.is_file()
            checks["credential_store_private"] = store.stat().st_mode & 0o077 == 0
        finally:
            stop(child)
        child, next_token = start(home)
        try:
            checks["restart_changes_launch_token"] = next_token != token
            checks["restart_rejects_old_launch_token"] = request(token)[0] == 401
            checks["restart_retains_signed_cookie"] = request("/", cookie)[0] == 200
        finally:
            stop(child)
    print(json.dumps(checks, indent=2))
    assert all(v for k, v in checks.items() if k not in {"staging_uid", "port", "live_credentials_copied"}), "Staging authentication check failed"


if __name__ == "__main__":
    main()
