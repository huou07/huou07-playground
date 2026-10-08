#!/usr/bin/env python3
"""Collect one CPU package-power sample for the unprivileged dashboard."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

POWER_FILE = Path("/var/lib/huou07-playground-power/sample.json")


def collect_power(binary: str | None = None, run=None) -> dict:
    turbostat = binary or shutil.which("turbostat")
    if not turbostat:
        return {"available": False, "reason": "turbostat is not installed."}
    runner = run or subprocess.run
    try:
        result = runner(
            [turbostat, "--quiet", "--Summary", "--show", "PkgWatt", "--interval", "1", "--num_iterations", "1"],
            capture_output=True, text=True, timeout=3, check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
        lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
        header = next((i for i, fields in enumerate(lines) if "PkgWatt" in fields), None)
        watts = None
        if result.returncode == 0 and header is not None and header + 1 < len(lines):
            value = lines[header + 1][lines[header].index("PkgWatt")]
            if value != "-":
                parsed = float(value)
                if math.isfinite(parsed) and 0 <= parsed <= 2000:
                    watts = round(parsed, 1)
        if watts is not None:
            return {"available": True, "watts": watts, "measurement": "CPU package power"}
        diagnostic = result.stderr.lower() + result.stdout.lower()
        if any(term in diagnostic for term in ("permission", "denied", "failed to access /dev/cpu/")):
            reason = "turbostat cannot read the required CPU power counters."
        else:
            reason = "turbostat returned no package-power value; hardware support or device access may be unavailable."
        return {"available": False, "reason": reason}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "turbostat did not return a sample within three seconds."}
    except (OSError, ValueError, IndexError):
        return {"available": False, "reason": "turbostat returned an unreadable package-power sample."}


def write_sample(path: Path = POWER_FILE, sample: dict | None = None) -> None:
    payload = dict(sample if sample is not None else collect_power())
    payload["sampled_at"] = time.time()
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".sample-", dir=path.parent)
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
    write_sample()
