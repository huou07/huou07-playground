#!/usr/bin/env python3
"""Small read-only Linux dashboard API and static file server."""
from __future__ import annotations

import json
import csv
import ipaddress
import io
import math
import os
import platform
import pwd
import re
import subprocess
import shutil
import socket
import socketserver
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
WG_EASY_SERVICE = "huou07-wg-easy.service"
WG_EASY_UNIT = Path("/etc/systemd/system") / WG_EASY_SERVICE
WG_STATUS_FILE = Path("/var/lib/huou07-wg-easy-status/status.json")
_prev_cpu: tuple[int, int, float] | None = None
_prev_net: tuple[float, dict[str, tuple[int, int]]] | None = None
_prev_processes: dict[int, tuple[int, int]] = {}
_prev_process_total: int | None = None
_prev_process_time: float | None = None
PRIVATE_WG_PORTS = (
    (9090, 9090),   # Cockpit, including Cockpit Files
    (4000, 4000),   # LiteLLM
    (51821, 51821), # wg-easy administration
    (14096, 4096),  # OpenCode Web
    (20128, 20128), # OmniRoute web UI
    (20129, 20129), # OmniRoute API
    (20132, 20132), # OmniRoute live updates
)
_private_proxy_slots = threading.BoundedSemaphore(32)


def read_text(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text()
    except (OSError, UnicodeError):
        return default


def wireguard_interface_addresses() -> list[str]:
    """Return private IPv4 addresses assigned to the WireGuard interface only."""
    binary = shutil.which("ip")
    if not binary:
        return []
    try:
        result = subprocess.run(
            [binary, "-j", "-4", "addr", "show", "dev", "wg0"],
            capture_output=True, text=True, timeout=2, check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
        if result.returncode != 0:
            return []
        links = json.loads(result.stdout)
    except (OSError, UnicodeError, TypeError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    addresses = []
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, dict) or link.get("ifname") != "wg0":
            continue
        info = link.get("addr_info", [])
        for address in info if isinstance(info, list) else []:
            if not isinstance(address, dict) or address.get("scope") != "global":
                continue
            try:
                parsed = ipaddress.ip_address(address.get("local", ""))
            except (TypeError, ValueError):
                continue
            if (
                parsed.version == 4 and parsed.is_private
                and not parsed.is_loopback and not parsed.is_link_local
                and not parsed.is_unspecified and not parsed.is_multicast
                and str(parsed) not in addresses
            ):
                addresses.append(str(parsed))
    return addresses


def cpu_package_power() -> dict:
    """Read a fresh, sanitized package-power sample from the restricted collector."""
    path = Path(os.environ.get("POWER_FILE", "/var/lib/huou07-playground-power/sample.json"))
    try:
        sample = json.loads(path.read_text())
        sampled_at = sample.get("sampled_at")
        age = time.time() - sampled_at if isinstance(sampled_at, (int, float)) and not isinstance(sampled_at, bool) else None
        if age is None or age < 0 or age > 60:
            return {"available": False, "reason": "No current CPU package-power sample is available."}
        if sample.get("available") is True:
            watts = sample.get("watts")
            if isinstance(watts, (int, float)) and not isinstance(watts, bool) and 0 <= watts <= 2000:
                return {"available": True, "watts": round(watts, 1), "measurement": "CPU package power"}
        reason = sample.get("reason")
        return {"available": False, "reason": reason[:160] if isinstance(reason, str) and reason else "CPU package power is unavailable."}
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return {"available": False, "reason": "No current CPU package-power sample is available."}


def gpu_metrics() -> dict:
    """Read available NVIDIA telemetry or a sanitized Intel GPU collector sample."""
    if platform.system() != "Linux":
        return {"available": False, "reason": "GPU telemetry is available when deployed on Linux."}
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return intel_gpu_metrics()
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        rows = list(csv.reader(io.StringIO(result.stdout)))
        if result.returncode != 0 or not rows or len(rows[0]) != 5:
            return {"available": False, "reason": "nvidia-smi could not read GPU telemetry."}
        name, usage, used, total, temperature = (value.strip() for value in rows[0])

        def number(value: str, maximum: float) -> float | None:
            if value.lower() in {"n/a", "[not supported]", ""}:
                return None
            parsed = float(value)
            return parsed if math.isfinite(parsed) and 0 <= parsed <= maximum else None

        usage_percent = number(usage, 100)
        memory_used_mib = number(used, 10_000_000)
        memory_total_mib = number(total, 10_000_000)
        temperature_c = number(temperature, 150)
        return {
            "available": True,
            "model": name[:120] or "NVIDIA GPU",
            "usage_percent": usage_percent,
            "memory_used": round(memory_used_mib * 1024 * 1024) if memory_used_mib is not None else None,
            "memory_total": round(memory_total_mib * 1024 * 1024) if memory_total_mib is not None else None,
            "temperature_c": temperature_c,
        }
    except (OSError, subprocess.TimeoutExpired, csv.Error, ValueError):
        return {"available": False, "reason": "nvidia-smi did not return a valid GPU sample."}


def intel_gpu_metrics() -> dict:
    """Read the short-lived, root-collected Intel i915 utilization sample."""
    path = Path(os.environ.get("GPU_FILE", "/var/lib/huou07-playground-gpu/sample.json"))
    try:
        sample = json.loads(path.read_text())
        sampled_at = sample.get("sampled_at")
        age = time.time() - sampled_at if isinstance(sampled_at, (int, float)) and not isinstance(sampled_at, bool) else None
        if age is None or age < 0 or age > 75:
            return {"available": False, "reason": "No current Intel GPU sample is available."}
        if sample.get("available") is True:
            usage = sample.get("usage_percent")
            if isinstance(usage, (int, float)) and not isinstance(usage, bool) and math.isfinite(usage) and 0 <= usage <= 100:
                engines = sample.get("engines")
                engines = {str(name)[:40]: round(value, 1) for name, value in engines.items() if isinstance(name, str) and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 100} if isinstance(engines, dict) else {}
                frequency = sample.get("frequency_mhz")
                frequency = round(frequency) if isinstance(frequency, (int, float)) and not isinstance(frequency, bool) and math.isfinite(frequency) and 0 < frequency <= 10000 else None
                rc6 = sample.get("rc6_percent")
                rc6 = round(rc6, 1) if isinstance(rc6, (int, float)) and not isinstance(rc6, bool) and math.isfinite(rc6) and 0 <= rc6 <= 100 else None
                return {"available": True, "model": "Intel integrated graphics (i915)", "usage_percent": round(usage, 1), "engines": engines, "frequency_mhz": frequency, "rc6_percent": rc6, "measurement": "Busiest GPU engine"}
        reason = sample.get("reason")
        return {"available": False, "reason": reason[:160] if isinstance(reason, str) and reason else "Intel GPU telemetry is unavailable."}
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return {"available": False, "reason": "No current Intel GPU sample is available."}


def storage_devices(sys_block: Path = Path("/sys/block")) -> list[dict]:
    """Describe physical block devices without reading identifiers or SMART data."""
    devices = []
    try:
        entries = sorted(sys_block.iterdir(), key=lambda item: item.name)
    except OSError:
        return devices
    for entry in entries:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", entry.name) or not (entry / "device").exists():
            continue
        try:
            sectors = int((entry / "size").read_text().strip())
            if sectors < 0:
                continue
        except (OSError, ValueError):
            sectors = None
        try:
            rotational = (entry / "queue/rotational").read_text().strip()
            kind = "HDD" if rotational == "1" else "SSD" if rotational == "0" else "Unknown"
        except OSError:
            kind = "Unknown"
        model = ""
        try:
            model = " ".join((entry / "device/model").read_text().split())[:100]
        except OSError:
            pass
        devices.append({"name": entry.name, "model": model or "Unknown model", "kind": kind, "size": sectors * 512 if sectors is not None else None})
    return devices


def swap_and_zram_metrics(swaps_text: str | None = None, sys_block: Path = Path("/sys/block")) -> tuple[dict, dict]:
    """Separate disk swap from compressed ZRAM usage and memory consumption."""
    if swaps_text is None:
        swaps_text = read_text("/proc/swaps")
    disk_swaps = []
    zram_swaps = {}
    for line in swaps_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        item = {"name": fields[0], "total": int(fields[2]) * 1024, "used": int(fields[3]) * 1024, "kind": fields[1]}
        if Path(fields[0]).name.startswith("zram"):
            zram_swaps[Path(fields[0]).name] = item
        else:
            disk_swaps.append(item)

    zram_devices = []
    try:
        devices = sorted(sys_block.glob("zram*"), key=lambda item: item.name)
    except OSError:
        devices = []
    for device in devices:
        try:
            total = int((device / "disksize").read_text().strip())
            stats = [int(value) for value in (device / "mm_stat").read_text().split()]
            zram_devices.append({
                "name": device.name,
                "total": total,
                "used": stats[0] if stats else 0,
                "compressed": stats[1] if len(stats) > 1 else None,
                "physical_used": stats[2] if len(stats) > 2 else None,
                "swap_used": zram_swaps.get(device.name, {}).get("used", 0),
            })
        except (OSError, ValueError):
            zram_devices.append({"name": device.name, "total": None, "used": None, "compressed": None, "physical_used": None, "swap_used": zram_swaps.get(device.name, {}).get("used", 0)})

    swap_total = sum(item["total"] for item in disk_swaps)
    swap_used = sum(item["used"] for item in disk_swaps)
    zram_total = sum(item["total"] or 0 for item in zram_devices)
    zram_used = sum(item["used"] or 0 for item in zram_devices)
    zram_compressed = sum(item["compressed"] or 0 for item in zram_devices)
    zram_physical_used = sum(item["physical_used"] or 0 for item in zram_devices)
    zram_swap_used = sum(item["swap_used"] or 0 for item in zram_devices)
    zram_swap_total = sum(zram_swaps.get(item["name"], {}).get("total", 0) for item in zram_devices)
    return (
        {"devices": disk_swaps, "used": swap_used, "total": swap_total, "percent": round(swap_used * 100 / swap_total) if swap_total else None},
        {"devices": zram_devices, "used": zram_used, "total": zram_total, "compressed": zram_compressed, "physical_used": zram_physical_used, "swap_used": zram_swap_used, "swap_total": zram_swap_total},
    )


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

    swaps, zram = swap_and_zram_metrics()

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
    return {
        "supported": True,
        "sampled_at": time.time(),
        "cpu": {"usage_percent": cpu_pct, "logical_cores": os.cpu_count(), "physical_cores": len(core_pairs) or None, "frequency_mhz": round(sum(frequencies) / len(frequencies)) if frequencies else None, "temperature_c": cpu_temperature, "model": model, "load": list(load) if load else None},
        "memory": {"used": ram_used, "total": total, "available": available, "percent": round(ram_used * 100 / total) if total else None},
        "storage": {"used": disk.used, "total": disk.total, "percent": round(disk.used * 100 / disk.total) if disk.total else None, "mount": "/"},
        "storage_devices": storage_devices(),
        "swap": swaps,
        "zram": zram,
        "network": {"interfaces": [{"name": name, "received_total": v[0], "sent_total": v[1]} for name, v in net.items()], "download_bytes_per_second": rx_rate, "upload_bytes_per_second": tx_rate},
        "system": {"os": platform.platform(), "kernel": platform.release(), "uptime_seconds": max(0, float(read_text("/proc/uptime", "0").split()[0]))},
        "gpu": gpu_metrics(),
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


def cockpit_files_status() -> dict:
    """Report whether the system-wide Cockpit Files package is installed and usable."""
    if platform.system() != "Linux":
        return {"available": False, "installed": False, "reason": "Cockpit Files is available when deployed on Linux."}
    package = any((Path(root) / "files" / "manifest.json").is_file() for root in ("/usr/share/cockpit", "/usr/local/share/cockpit"))
    if not package:
        return {"available": False, "installed": False, "reason": "Cockpit Files is not installed."}
    cockpit = cockpit_status()
    if not cockpit["available"]:
        return {"available": False, "installed": True, "reason": "Cockpit Files is installed, but Cockpit is unavailable."}
    return {"available": True, "installed": True}


def wg_easy_needs_setup() -> bool:
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:
            return None

    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(Request("http://127.0.0.1:51821/", headers={"User-Agent": "huou07-playground/0.1"}), timeout=1)
        response.close()
        return False
    except HTTPError as error:
        return 300 <= error.code < 400 and urlsplit(error.headers.get("Location", "")).path.startswith("/setup/")
    except (OSError, URLError, ValueError):
        return False


def wg_status_sample() -> dict | None:
    try:
        sample = json.loads(Path(os.environ.get("WG_STATUS_FILE", str(WG_STATUS_FILE))).read_text())
        now = time.time()
        sampled_at = sample.get("sampled_at")
        peer_count = sample.get("peer_count")
        handshake = sample.get("latest_handshake_at")
        if (
            sample.get("available") is not True
            or not isinstance(sampled_at, (int, float))
            or isinstance(sampled_at, bool)
            or not math.isfinite(sampled_at)
            or now - sampled_at < 0
            or now - sampled_at > 90
            or not isinstance(peer_count, int)
            or isinstance(peer_count, bool)
            or not 0 <= peer_count <= 65535
            or (handshake is not None and (not isinstance(handshake, int) or isinstance(handshake, bool) or not 0 < handshake <= now + 30))
        ):
            return None
        return {"peer_count": peer_count, "latest_handshake_at": handshake}
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return None


def vpn_status() -> dict:
    if platform.system() != "Linux":
        unavailable = {"available": False, "connected": False, "state": "Unavailable"}
        return {**unavailable, "wireguard": unavailable, "tailscale": unavailable}
    client = shutil.which("tailscale")
    if not client:
        tailnet = {"available": False, "connected": False, "state": "Unavailable"}
    else:
        try:
            result = subprocess.run([client, "status", "--json"], capture_output=True, text=True, timeout=2, check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
            data = json.loads(result.stdout) if result.returncode == 0 else {}
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            data = {}
        connected = data.get("BackendState") == "Running"
        tailnet = {"available": True, "connected": connected, "state": "Connected" if connected else "Disconnected"}

    if not WG_EASY_UNIT.is_file():
        wireguard = {"available": False, "connected": False, "state": "Not installed", "peer_count": 0}
    else:
        try:
            service = subprocess.run(["systemctl", "is-active", "--quiet", WG_EASY_SERVICE], capture_output=True, text=True, timeout=2, check=False, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        except (OSError, subprocess.TimeoutExpired):
            service = None
        if service is None or service.returncode != 0:
            wireguard = {"available": False, "connected": False, "state": "Stopped", "peer_count": 0}
        else:
            sample = wg_status_sample()
            if sample is None:
                setup_required = wg_easy_needs_setup()
                wireguard = {"available": True, "connected": False, "state": "Needs owner setup" if setup_required else "Status unavailable", "peer_count": 0}
            elif sample["peer_count"] == 0:
                setup_required = wg_easy_needs_setup()
                wireguard = {"available": True, "connected": False, "state": "Needs owner setup" if setup_required else "Waiting for peer", "peer_count": 0}
            else:
                latest = sample["latest_handshake_at"]
                age = max(0, int(time.time()) - latest) if latest else None
                connected = age is not None and age <= 180
                wireguard = {
                    "available": True,
                    "connected": connected,
                    "state": "Connected" if connected else "Waiting for peer",
                    "peer_count": sample["peer_count"],
                    "last_handshake_seconds": age,
                }
    return {"available": wireguard["available"], "connected": wireguard["connected"], "state": wireguard["state"], "wireguard": wireguard, "tailscale": tailnet}


def valid_app_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not any(char.isspace() for char in parsed.hostname) and (port is None or 1 <= port <= 65535) and parsed.username is None and parsed.password is None
    except ValueError:
        return False


def valid_health_url(value: object) -> bool:
    if not valid_app_url(value):
        return False
    try:
        return urlsplit(value).hostname.casefold() in {"127.0.0.1", "localhost", "::1"}
    except (AttributeError, ValueError):
        return False


def dashboard_same_origin_request_allowed(origin_header: str, host_header: str, bind_address: str) -> bool:
    """Allow mutations only from the origin used to reach this exact listener."""
    origin = urlsplit(origin_header)
    try:
        request = urlsplit(f"http://{host_header}")
    except ValueError:
        return False
    request_host = request.hostname
    if (
        origin.scheme not in {"http", "https"}
        or origin.netloc.casefold() != host_header.casefold()
        or request_host is None
        or request.username is not None
        or request.password is not None
        or request.path
        or request.query
        or request.fragment
    ):
        return False
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if bind_address in loopback_hosts:
        return request_host in loopback_hosts
    return request_host == bind_address


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
    except HTTPError as error:
        if 300 <= error.code < 400:
            return "available"
        return "authentication_required" if error.code == 401 else "unavailable"
    except (OSError, URLError, ValueError):
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
        if health_url is not None and not valid_health_url(health_url):
            raise ValueError
        if management_url is not None and not valid_app_url(management_url):
            raise ValueError
        if health_method not in {"GET", "HEAD"}:
            raise ValueError
        if any(item["name"].casefold() == name.strip().casefold() for item in apps):
            raise ValueError
        apps.append({"name": name.strip(), "url": url, "description": description, "category": category, "health_url": health_url, "health_method": health_method, "management_url": management_url})
    return apps


def save_app_registry(config: object) -> None:
    """Atomically save the non-executable app list in the service-owned config dir."""
    apps = validate_app_entries(config)
    path = Path(os.environ.get("APPS_FILE", "/var/lib/huou07-playground/apps.json"))
    if path.parent.is_symlink() or not path.parent.is_dir() or path.is_symlink() or not path.is_file():
        raise OSError("Application registry path is unavailable.")
    group_id = path.stat().st_gid
    data = json.dumps({"apps": apps}, separators=(",", ":")).encode()
    fd, temporary = tempfile.mkstemp(prefix=".apps-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchown(output.fileno(), os.geteuid(), group_id)
            os.fchmod(output.fileno(), 0o660)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def app_registry() -> dict:
    path = Path(os.environ.get("APPS_FILE", "/var/lib/huou07-playground/apps.json"))
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


def mutate_app_registry(change: object) -> None:
    if not isinstance(change, dict):
        raise ValueError
    path = Path(os.environ.get("APPS_FILE", "/var/lib/huou07-playground/apps.json"))
    current = validate_app_entries(json.loads(path.read_text()))
    action = change.get("action")
    name = change.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError
    match = next((index for index, item in enumerate(current) if item["name"].casefold() == name.strip().casefold()), None)
    if action == "add":
        item = validate_app_entries({"apps": [change.get("app")]})[0]
        if match is not None:
            raise ValueError
        current.append(item)
    elif action == "update":
        if match is None:
            raise ValueError
        item = validate_app_entries({"apps": [change.get("app")]})[0]
        if "health_url" not in change["app"]:
            item["health_url"] = current[match]["health_url"]
            item["health_method"] = current[match]["health_method"]
        current[match] = item
    elif action == "delete":
        if match is None:
            raise ValueError
        del current[match]
    else:
        raise ValueError
    save_app_registry({"apps": current})


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
        if self.path == "/api/files":
            self.send_json(200, cockpit_files_status())
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

    def do_POST(self) -> None:
        if self.path != "/api/apps":
            self.send_error(404)
            return
        host_header = self.headers.get("Host", "")
        bind_address = self.server.server_address[0]
        if not dashboard_same_origin_request_allowed(self.headers.get("Origin", ""), host_header, bind_address):
            self.send_json(403, {"error": "Application changes must come from this dashboard."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Send application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if length < 0 or length > 65536:
            self.send_json(413 if length > 65536 else 400, {"error": "Invalid application registry size."})
            return
        try:
            change = json.loads(self.rfile.read(length))
            mutate_app_registry(change)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            self.send_json(400, {"error": "Application registry is invalid or could not be saved."})
            return
        self.send_json(200, app_registry())

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


class InterfaceBoundHTTPServer(HTTPServer):
    """HTTP listener limited to traffic arriving through one device."""
    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], interface: str):
        self.interface = interface
        super().__init__(server_address, handler)

    def server_bind(self) -> None:
        option = getattr(socket, "SO_BINDTODEVICE", None)
        if option is None:
            raise OSError("Interface-bound listeners are not supported on this platform.")
        self.socket.setsockopt(socket.SOL_SOCKET, option, self.interface.encode("ascii") + b"\0")
        super().server_bind()


class PrivateProxyHandler(socketserver.BaseRequestHandler):
    """Bounded-memory TCP relay to a fixed loopback application port."""
    def handle(self) -> None:
        try:
            upstream = socket.create_connection(("127.0.0.1", self.server.backend_port), timeout=3)
        except OSError:
            return
        client = self.request
        client.settimeout(None)
        upstream.settimeout(None)

        def forward(source: socket.socket, destination: socket.socket) -> None:
            try:
                while True:
                    chunk = source.recv(65536)
                    if not chunk:
                        break
                    destination.sendall(chunk)
            except OSError:
                pass
            finally:
                try:
                    destination.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        sender = threading.Thread(target=forward, args=(client, upstream), daemon=True)
        sender.start()
        try:
            forward(upstream, client)
        finally:
            for connection in (client, upstream):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            sender.join(timeout=1)


class PrivateProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """TCP relay listener restricted to the WireGuard device."""
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def __init__(self, server_address: tuple[str, int], backend_port: int, interface: str):
        self.backend_port = backend_port
        self.interface = interface
        super().__init__(server_address, PrivateProxyHandler)

    def server_bind(self) -> None:
        option = getattr(socket, "SO_BINDTODEVICE", None)
        if option is None:
            raise OSError("Interface-bound listeners are not supported on this platform.")
        self.socket.setsockopt(socket.SOL_SOCKET, option, self.interface.encode("ascii") + b"\0")
        super().server_bind()

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not _private_proxy_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            _private_proxy_slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            _private_proxy_slots.release()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Only loopback binding is supported until authentication and private-network access controls are implemented.")
    port = int(os.environ.get("PORT", "8765"))
    servers = [HTTPServer((host, port), Handler)]
    wg_servers = []
    print(f"huou07 playground loopback listener ready on port {port}")
    for address in wireguard_interface_addresses():
        try:
            server = InterfaceBoundHTTPServer((address, port), Handler, "wg0")
        except OSError:
            print("WireGuard dashboard listener unavailable; loopback access remains active.")
            continue
        servers.append(server)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
        worker.start()
        wg_servers.append(server)
        for listen_port, backend_port in PRIVATE_WG_PORTS:
            try:
                proxy = PrivateProxyServer((address, listen_port), backend_port, "wg0")
            except OSError:
                print("A private application listener is unavailable; its loopback service remains active.")
                continue
            servers.append(proxy)
            worker = threading.Thread(target=proxy.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
            worker.start()
            wg_servers.append(proxy)
        print("WireGuard dashboard listener ready on the private wg0 interface.")
    try:
        servers[0].serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for server in wg_servers:
            server.shutdown()
        for server in servers:
            server.server_close()


if __name__ == "__main__":
    main()
