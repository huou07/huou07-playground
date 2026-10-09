#!/usr/bin/env python3
"""Publish a secret-free WireGuard peer and handshake summary for the dashboard."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

STATUS_FILE = Path("/var/lib/huou07-wg-easy-status/status.json")


def parse_latest_handshakes(output: str) -> tuple[int, int | None]:
    peers: list[int] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            peers.append(max(0, int(fields[1])))
        except ValueError:
            continue
    if not peers:
        return 0, None
    latest = max(peers)
    return len(peers), latest or None


def collect_status(binary: str | None = None, run=None) -> dict:
    tool = binary or shutil.which("wg")
    if not tool:
        return {"available": False}
    runner = run or subprocess.run
    try:
        result = runner(
            [tool, "show", "wg0", "latest-handshakes"], capture_output=True,
            text=True, timeout=2, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}
    if result.returncode != 0:
        return {"available": False}
    peer_count, latest = parse_latest_handshakes(result.stdout or "")
    return {
        "available": True,
        "peer_count": peer_count,
        "latest_handshake_at": latest,
        "sampled_at": time.time(),
    }


def write_status(path: Path = STATUS_FILE, status: dict | None = None) -> None:
    payload = dict(status if status is not None else collect_status())
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".status-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(payload, output, separators=(",", ":"))
            output.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    if len(os.sys.argv) != 1:
        raise SystemExit("This fixed-purpose collector takes no arguments.")
    write_status()
