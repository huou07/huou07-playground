#!/usr/bin/env python3
"""Small read-only Linux dashboard API and static file server."""
from __future__ import annotations

import json
import os
import platform
import pwd
import re
import subprocess
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
_prev_cpu: tuple[int, int, float] | None = None
_prev_net: tuple[float, dict[str, tuple[int, int]]] | None = None
_prev_processes: dict[int, tuple[int, int]] = {}
_prev_process_total: int | None = None
_prev_process_time: float | None = None
_power_sample: tuple[float, dict] | None = None


def read_text(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text()
    except (OSError, UnicodeError):
        return default


def cpu_package_power() -> dict:
    """Read one summary-only turbostat package-power sample, cached briefly."""
    global _power_sample
    now = time.monotonic()
    if _power_sample and now - _power_sample[0] < 15:
        return _power_sample[1]
    turbostat = shutil.which("turbostat")
    if not turbostat:
        result = {"available": False, "reason": "turbostat is not installed."}
    else:
        try:
            sample = subprocess.run(
                [turbostat, "--quiet", "--Summary", "--show", "PkgWatt", "--interval", "1", "--num_iterations", "1"],
                capture_output=True, text=True, timeout=3, check=False,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
            lines = [line.split() for line in sample.stdout.splitlines() if line.strip()]
            header = next((i for i, fields in enumerate(lines) if "PkgWatt" in fields), None)
            watts = None
            if sample.returncode == 0 and header is not None and header + 1 < len(lines):
                column = lines[header].index("PkgWatt")
                value = lines[header + 1][column]
                if value != "-":
                    parsed = float(value)
                    if 0 <= parsed <= 2000:
                        watts = round(parsed, 1)
            if watts is not None:
                result = {"available": True, "watts": watts, "measurement": "CPU package power"}
            elif any(term in sample.stderr.lower() for term in ("permission", "denied", "failed to access /dev/cpu/")):
                result = {"available": False, "reason": "turbostat cannot read the required CPU power counters with the current service permissions."}
            else:
                result = {"available": False, "reason": "This CPU or kernel does not expose package power through turbostat."}
        except subprocess.TimeoutExpired:
            result = {"available": False, "reason": "turbostat did not return a sample within three seconds."}
        except (OSError, ValueError, IndexError):
            result = {"available": False, "reason": "turbostat returned an unreadable package-power sample."}
    _power_sample = (now, result)
    return result


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
        if 0 < now - _prev_cpu[2] <= 30 and total_delta > 0:
            cpu_pct = round(max(0, min(100, (total_delta - idle_delta) * 100 / total_delta)))
    _prev_cpu = (cpu_total, cpu_idle, now)

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
        if 0 < elapsed <= 30:
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
        "system": {"os": platform.platform(), "kernel": platform.release(), "uptime_seconds": max(0, float(read_text("/proc/uptime", "0").split()[0]))},
        "gpu": {"available": False, "reason": "No supported GPU telemetry adapter is configured."},
        "power": cpu_package_power(),
    }


def process_metrics() -> dict:
    global _prev_processes, _prev_process_total, _prev_process_time
    if platform.system() != "Linux":
        return {"available": False, "reason": "Process metrics are available when deployed on Linux."}
    cpu_line = read_text("/proc/stat").splitlines()
    cpu_values = [int(value) for value in cpu_line[0].split()[1:]] if cpu_line and cpu_line[0].startswith("cpu ") else []
    total_ticks = sum(cpu_values) - sum(cpu_values[8:10])
    total_delta = total_ticks - _prev_process_total if _prev_process_total is not None else 0
    sample_gap = time.monotonic() - _prev_process_time if _prev_process_time is not None else None
    cores = os.cpu_count() or 1
    ram_total = 0
    for line in read_text("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            try:
                ram_total = int(line.split()[1]) * 1024
            except (ValueError, IndexError):
                pass
            break
    processes = []
    current = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            pid = int(proc.name)
            stat = read_text(str(proc / "stat"))
            close = stat.rfind(")")
            fields = stat[close + 1:].split()
            if close < 0 or len(fields) <= 19:
                continue
            ticks = int(fields[11]) + int(fields[12])
            started = int(fields[19])
            current[pid] = (ticks, started)
            previous = _prev_processes.get(pid)
            cpu_percent = None
            if previous and previous[1] == started and sample_gap is not None and 0 < sample_gap <= 30 and total_delta > 0:
                cpu_percent = round(max(0, (ticks - previous[0]) * cores * 100 / total_delta), 1)
            uid = None
            rss = 0
            for line in read_text(str(proc / "status")).splitlines():
                if line.startswith("Uid:"):
                    try:
                        uid = int(line.split()[1])
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("VmRSS:"):
                    try:
                        rss = int(line.split()[1]) * 1024
                    except (ValueError, IndexError):
                        pass
            try:
                owner = pwd.getpwuid(uid).pw_name if uid is not None else "unknown"
            except KeyError:
                owner = str(uid) if uid is not None else "unknown"
            name = read_text(str(proc / "comm")).strip() or stat[stat.find("(") + 1:close]
            processes.append({"pid": pid, "name": name, "owner": owner, "cpu_percent": cpu_percent, "memory_bytes": rss, "memory_percent": round(rss * 100 / ram_total, 2) if ram_total else None})
        except (OSError, ValueError, IndexError):
            continue
    _prev_processes = current
    _prev_process_total = total_ticks
    _prev_process_time = time.monotonic()
    processes.sort(key=lambda item: (item["cpu_percent"] or 0, item["memory_bytes"]), reverse=True)
    return {"available": True, "sampled_at": time.time(), "total": len(processes), "processes": processes[:1000]}


def service_metrics() -> dict:
    if platform.system() != "Linux":
        return {"available": False, "reason": "Systemd service data is available when deployed on Linux."}
    try:
        result = subprocess.run(["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-pager", "--no-legend"], capture_output=True, text=True, timeout=3, check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "systemctl could not provide service data."}
    if result.returncode != 0:
        return {"available": False, "reason": "systemctl could not provide service data."}
    units = []
    for line in result.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) >= 4:
            units.append({"name": fields[0], "load": fields[1], "active": fields[2], "state": fields[3], "description": fields[4][:100] if len(fields) > 4 else ""})
    units.sort(key=lambda unit: (unit["active"] != "active", unit["name"].casefold()))
    return {"available": True, "sampled_at": time.time(), "total": len(units), "services": units}


def cockpit_status() -> dict:
    if platform.system() != "Linux":
        return {"available": False, "reason": "Cockpit is available when deployed on Linux."}
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", "cockpit.socket"], capture_output=True, timeout=2, check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "Cockpit status could not be checked."}
    return {"available": result.returncode == 0, "reason": "Cockpit is not installed or its socket is stopped."}


def vpn_status() -> dict:
    if platform.system() != "Linux":
        return {"available": False, "connected": False, "reason": "VPN status is available when deployed on Linux."}
    client = shutil.which("tailscale")
    if not client:
        return {"available": False, "connected": False, "reason": "No supported VPN client was found."}
    try:
        result = subprocess.run([client, "status", "--json"], capture_output=True, text=True, timeout=2, check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        data = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        data = {}
    connected = data.get("BackendState") == "Running"
    return {"available": True, "connected": connected, "state": "Connected" if connected else "Disconnected"}


def valid_app_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not any(char.isspace() for char in parsed.hostname) and (port is None or 1 <= port <= 65535) and parsed.username is None and parsed.password is None
    except ValueError:
        return False


def app_health(url: str, method: str) -> str:
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:
            return None

    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        request = Request(url, method=method, headers={"User-Agent": "huou07-playground/0.1"})
        response = opener.open(request, timeout=1)
        try:
            return "available" if 200 <= response.status < 400 else "unavailable"
        finally:
            response.close()
    except (OSError, HTTPError, URLError, ValueError):
        return "unavailable"


def validate_app_entries(config: object) -> list[dict]:
    entries = config.get("apps") if isinstance(config, dict) else None
    if not isinstance(entries, list) or len(entries) > 20:
        raise ValueError
    apps = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError
        name = entry.get("name")
        url = entry.get("url")
        description = entry.get("description", "")
        category = entry.get("category", "Application")
        health_url = entry.get("health_url")
        health_method = entry.get("health_method", "GET")
        management_url = entry.get("management_url")
        if not isinstance(name, str) or not name.strip() or len(name) > 60 or not valid_app_url(url):
            raise ValueError
        if not isinstance(description, str) or len(description) > 160 or not isinstance(category, str) or len(category) > 40:
            raise ValueError
        if health_url is not None and not valid_app_url(health_url):
            raise ValueError
        if management_url is not None and not valid_app_url(management_url):
            raise ValueError
        if health_method not in {"GET", "HEAD"}:
            raise ValueError
        apps.append({"name": name.strip(), "url": url, "description": description, "category": category, "health_url": health_url, "health_method": health_method, "management_url": management_url})
    return apps


def app_registry() -> dict:
    path = Path(os.environ.get("APPS_FILE", "/etc/huou07-playground/apps.json"))
    try:
        apps = validate_app_entries(json.loads(path.read_text()))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return {"available": False, "reason": "Application configuration is unavailable or invalid.", "apps": []}

    with ThreadPoolExecutor(max_workers=8) as pool:
        checks = [pool.submit(app_health, item["health_url"], item["health_method"]) if item["health_url"] else None for item in apps]
        result = []
        for item, check in zip(apps, checks):
            result.append({"name": item["name"], "url": item["url"], "description": item["description"], "category": item["category"], "management_url": item["management_url"], "status": check.result() if check else "unmonitored"})
    return {"available": True, "sampled_at": time.time(), "total": len(result), "apps": result}


class Handler(BaseHTTPRequestHandler):
    server_version = "Huou07Playground/0.1"

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json(200, {"ok": True})
            return
        if self.path == "/api/metrics":
            self.send_json(200, linux_metrics())
            return
        if self.path == "/api/processes":
            self.send_json(200, process_metrics())
            return
        if self.path == "/api/services":
            self.send_json(200, service_metrics())
            return
        if self.path == "/api/cockpit":
            self.send_json(200, cockpit_status())
            return
        if self.path == "/api/vpn":
            self.send_json(200, vpn_status())
            return
        if self.path == "/api/apps":
            self.send_json(200, app_registry())
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
