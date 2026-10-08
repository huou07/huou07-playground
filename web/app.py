#!/usr/bin/env python3
"""Small read-only Linux dashboard API and static file server."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
_prev_cpu: tuple[int, int] | None = None
_prev_net: tuple[float, dict[str, tuple[int, int]]] | None = None


def read_text(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text()
    except (OSError, UnicodeError):
        return default


def linux_metrics() -> dict:
    global _prev_cpu, _prev_net
    if platform.system() != "Linux":
        return {"supported": False, "reason": "Linux host metrics are available when deployed on Linux."}

    now = time.monotonic()
    cpu = read_text("/proc/stat").splitlines()
    cpu_values = [int(v) for v in cpu[0].split()[1:]] if cpu and cpu[0].startswith("cpu ") else []
    cpu_total = sum(cpu_values) - sum(cpu_values[8:10])
    cpu_idle = cpu_values[3] + (cpu_values[4] if len(cpu_values) > 4 else 0) if cpu_values else 0
    cpu_pct = None
    if _prev_cpu:
        total_delta, idle_delta = cpu_total - _prev_cpu[0], cpu_idle - _prev_cpu[1]
        if total_delta > 0:
            cpu_pct = round(max(0, min(100, (total_delta - idle_delta) * 100 / total_delta)))
    _prev_cpu = (cpu_total, cpu_idle)

    mem = {}
    for line in read_text("/proc/meminfo").splitlines():
        match = re.match(r"(\w+):\s+(\d+)", line)
        if match:
            mem[match.group(1)] = int(match.group(2)) * 1024
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    ram_used = max(0, total - available)

    swaps = []
    for line in read_text("/proc/swaps").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4:
            swaps.append({"name": fields[0], "total": int(fields[2]) * 1024, "used": int(fields[3]) * 1024, "kind": fields[1]})
    swap_total = sum(item["total"] for item in swaps)
    swap_used = sum(item["used"] for item in swaps)

    net = {}
    for line in read_text("/proc/net/dev").splitlines()[2:]:
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        fields = values.split()
        interface = name.strip()
        if len(fields) >= 9 and interface != "lo":
            sys_device = Path("/sys/class/net") / interface
            if (sys_device / "device").exists() and read_text(str(sys_device / "operstate")).strip() == "up":
                net[interface] = (int(fields[0]), int(fields[8]))
    rx_rate = tx_rate = None
    if _prev_net and net:
        elapsed = now - _prev_net[0]
        if elapsed > 0:
            rx_rate = sum(max(0, v[0] - _prev_net[1].get(k, v)[0]) for k, v in net.items()) / elapsed
            tx_rate = sum(max(0, v[1] - _prev_net[1].get(k, v)[1]) for k, v in net.items()) / elapsed
    _prev_net = (now, net)

    disk = shutil.disk_usage("/")
    cpuinfo = read_text("/proc/cpuinfo")
    cpu_lines = cpuinfo.splitlines()
    model = next((line.split(":", 1)[1].strip() for line in cpu_lines if line.startswith("model name") and ":" in line), platform.processor() or "Unknown")
    core_pairs = set()
    for block in cpuinfo.split("\n\n"):
        physical = re.search(r"^physical id\s*:\s*(\d+)", block, re.M)
        core = re.search(r"^core id\s*:\s*(\d+)", block, re.M)
        if physical and core:
            core_pairs.add((physical.group(1), core.group(1)))
    frequencies = []
    for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_cur_freq"):
        try:
            frequencies.append(int(path.read_text().strip()) / 1000)
        except (OSError, ValueError):
            pass
    if not frequencies:
        frequencies = [float(match.group(1)) for line in cpu_lines if (match := re.match(r"cpu MHz\s*:\s*([0-9.]+)", line))]
    cpu_temperature = None
    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        name = read_text(str(hwmon / "name")).strip().lower()
        for label_path in hwmon.glob("temp*_label"):
            label = read_text(str(label_path)).strip().lower()
            if not any(word in f"{name} {label}" for word in ("package", "tctl", "tdie", "cpu")):
                continue
            input_path = label_path.with_name(label_path.name.removesuffix("_label") + "_input")
            try:
                value = int(input_path.read_text().strip()) / 1000
                if -20 <= value <= 150:
                    cpu_temperature = round(max(cpu_temperature or value, value), 1)
            except (OSError, ValueError):
                pass
    if cpu_temperature is None:
        for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
            if read_text(str(zone / "type")).strip().lower() not in {"x86_pkg_temp", "cpu-thermal"}:
                continue
            try:
                value = int((zone / "temp").read_text().strip()) / 1000
                if -20 <= value <= 150:
                    cpu_temperature = round(value, 1)
                    break
            except (OSError, ValueError):
                pass
    load = os.getloadavg() if hasattr(os, "getloadavg") else None
    zram = []
    for device in Path("/sys/block").glob("zram*"):
        try:
            total_bytes = int((device / "disksize").read_text().strip())
            stats = (device / "mm_stat").read_text().split()
            used_bytes = int(stats[0]) if stats else 0
            zram.append({"name": device.name, "total": total_bytes, "used": used_bytes, "compressed": int(stats[1]) if len(stats) > 1 else None, "physical_used": int(stats[2]) if len(stats) > 2 else None})
        except (OSError, ValueError):
            zram.append({"name": device.name, "total": None, "used": None})

    return {
        "supported": True,
        "sampled_at": time.time(),
        "cpu": {"usage_percent": cpu_pct, "logical_cores": os.cpu_count(), "physical_cores": len(core_pairs) or None, "frequency_mhz": round(sum(frequencies) / len(frequencies)) if frequencies else None, "temperature_c": cpu_temperature, "model": model, "load": list(load) if load else None},
        "memory": {"used": ram_used, "total": total, "available": available, "percent": round(ram_used * 100 / total) if total else None},
        "storage": {"used": disk.used, "total": disk.total, "percent": round(disk.used * 100 / disk.total) if disk.total else None, "mount": "/"},
        "swap": {"devices": swaps, "used": swap_used, "total": swap_total, "percent": round(swap_used * 100 / swap_total) if swap_total else None},
        "zram": {"devices": zram, "used": sum(x["used"] or 0 for x in zram), "total": sum(x["total"] or 0 for x in zram)},
        "network": {"interfaces": [{"name": name, "received_total": v[0], "sent_total": v[1]} for name, v in net.items()], "download_bytes_per_second": rx_rate, "upload_bytes_per_second": tx_rate},
        "system": {"os": platform.platform(), "kernel": platform.release(), "uptime_seconds": max(0, time.time() - float(read_text("/proc/uptime", "0").split()[0]))},
        "gpu": {"available": False, "reason": "No supported GPU telemetry adapter is configured."},
        "power": {"available": False, "reason": "CPU package power is unavailable until turbostat is installed and safely configured."},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "Huou07Playground/0.1"

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json(200, {"ok": True})
            return
        if self.path == "/api/metrics":
            self.send_json(200, linux_metrics())
            return
        path = "/index.html" if self.path == "/" else self.path
        target = (STATIC / path.lstrip("/")).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8" if target.suffix == ".js" else "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, value: dict) -> None:
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep client addresses and request paths out of routine logs.
        return


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Only loopback binding is supported until authentication and private-network access controls are implemented.")
    port = int(os.environ.get("PORT", "8765"))
    server = HTTPServer((host, port), Handler)
    print(f"huou07 playground listening on {host}:{port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
