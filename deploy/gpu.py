#!/usr/bin/env python3
"""Collect a bounded Intel i915 GPU sample for the unprivileged dashboard."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

GPU_FILE = Path("/var/lib/huou07-playground-gpu/sample.json")


def last_json_sample(output: str) -> dict | None:
    """Read the last complete object from intel_gpu_top's streaming JSON array."""
    decoder = json.JSONDecoder()
    start = output.find("[")
    if start < 0:
        return None
    offset = start + 1
    latest = None
    while offset < len(output):
        while offset < len(output) and (output[offset].isspace() or output[offset] == ","):
            offset += 1
        if offset >= len(output) or output[offset] == "]":
            break
        try:
            item, offset = decoder.raw_decode(output, offset)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            latest = item
    return latest


def collect_gpu(binary: str | None = None, run=None) -> dict:
    tool = binary or shutil.which("intel_gpu_top")
    if not tool:
        return {"available": False, "reason": "intel-gpu-tools is not installed."}
    if not any((card / "device/driver").resolve().name == "i915" for card in Path("/sys/class/drm").glob("card[0-9]*") if card.name[4:].isdigit()):
        return {"available": False, "reason": "No Intel i915 graphics device is available."}
    runner = run or subprocess.run
    try:
        result = runner(
            [tool, "-J", "-s", "1000"], capture_output=True, text=True, timeout=3,
            check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        output = result.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
    except OSError:
        return {"available": False, "reason": "intel_gpu_top could not read Intel GPU telemetry."}

    sample = last_json_sample(output)
    raw_engines = sample.get("engines") if sample else None
    if not isinstance(raw_engines, dict):
        return {"available": False, "reason": "intel_gpu_top returned no complete GPU sample."}
    engines = {}
    for name, values in raw_engines.items():
        if not isinstance(name, str) or not isinstance(values, dict):
            continue
        busy = values.get("busy")
        if isinstance(busy, (int, float)) and not isinstance(busy, bool) and math.isfinite(busy) and 0 <= busy <= 100:
            engines[name[:40]] = round(busy, 1)
    if not engines:
        return {"available": False, "reason": "intel_gpu_top returned no usable engine counters."}
    usage = max(engines.values())
    frequency = sample.get("frequency", {}).get("actual") if isinstance(sample.get("frequency"), dict) else None
    rc6 = sample.get("rc6", {}).get("value") if isinstance(sample.get("rc6"), dict) else None
    return {
        "available": True,
        "usage_percent": usage,
        "engines": engines,
        "frequency_mhz": frequency if isinstance(frequency, (int, float)) and not isinstance(frequency, bool) and math.isfinite(frequency) and 0 < frequency <= 10000 else None,
        "rc6_percent": rc6 if isinstance(rc6, (int, float)) and not isinstance(rc6, bool) and math.isfinite(rc6) and 0 <= rc6 <= 100 else None,
    }


def write_sample(path: Path = GPU_FILE, sample: dict | None = None) -> None:
    payload = dict(sample if sample is not None else collect_gpu())
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
