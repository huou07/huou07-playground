#!/usr/bin/env python3
"""Read-only worker probe. Opens protected files without reading their contents."""
import http.client
import json
import os
import socket
import subprocess
from pathlib import Path


def can_open(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        os.close(fd)
        return True
    except OSError:
        return False


def launch_endpoint_exposes_token(port=8765):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", "/api/apps/launch?name=DeepSeek+Harness")
        response = connection.getresponse()
        # Never print, save, redeem, or follow the Location header.
        return "token=" in response.getheader("Location", "")
    except OSError:
        return None
    finally:
        connection.close()


def probe():
    if os.geteuid() != 987:
        raise SystemExit("Run this probe as agents-worker (987); refusing another identity.")
    checks = {}
    runtime = Path("/home/agents-worker/.agent-workbench-runtime-v6")
    paths = {
        "worker_dsh_credentials": runtime / ".dsh/.credentials.yaml",
        "worker_codex_auth": runtime / ".codex/auth.json",
        "trusted_dsh_credentials": Path("/var/lib/huou07-dsh/dsh/.credentials.yaml"),
        "trusted_codex_auth": Path("/var/lib/huou07-dsh/.codex/auth.json"),
        "launch_token": Path("/run/huou07-dsh-link/url"),
    }
    for label, path in paths.items():
        # Missing files cannot establish successful isolation of a live store.
        try:
            exists = path.exists()
        except OSError:
            exists = None
        checks[label] = {"readable": can_open(path), "exists": exists}
    trusted_paths = [
        "/usr/local/libexec/agent-workbench/worker-web-v7",
        "/usr/local/libexec/agent-workbench/worker-exec-v7",
        "/srv/agent-workbench/skills", "/srv/agent-workbench/AGENTS.md",
        "/srv/agent-workbench/dsh-global",
        "/home/huou07/.local/lib/node_modules/@deepseek-ai/dsh",
    ]
    checks["writable_paths"] = {p: os.access(p, os.W_OK) for p in trusted_paths}
    checks["dashboard_returns_launch_token"] = launch_endpoint_exposes_token()
    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    peer.settimeout(2)
    try:
        peer.connect("/run/dsh-acp.sock")
        checks["owner_acp_socket_connectable"] = True
    except OSError:
        checks["owner_acp_socket_connectable"] = False
    finally:
        peer.close()
    for unit in ["agent-workbench-dsh@3080.service", "agent-workbench-opencode-web.service"]:
        result = subprocess.run(["/usr/bin/systemctl", "show", unit, "-p", "MainPID", "--value"],
                                capture_output=True, text=True, timeout=5, check=True)
        pid = int(result.stdout.strip())
        checks[unit] = {"pid": pid, "uid": os.stat(f"/proc/{pid}").st_uid,
                        "environ_openable": can_open(f"/proc/{pid}/environ")}
        try:
            list(Path(f"/proc/{pid}/fd").iterdir())
            checks[unit]["fd_listable"] = True
        except OSError:
            checks[unit]["fd_listable"] = False
    return {"probe_uid": os.geteuid(), "probe_groups": os.getgroups(), "checks": checks,
            "acceptance": "INCOMPLETE: metadata probe is not an agent turn or a functional test"}


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
