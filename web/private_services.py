"""Read the one source of truth for private relay, firewall and SSH ports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[1] / "deploy" / "private-services.json"
PORT_FIELDS = ("backend_port", "wireguard_port")
SSH_GROUPS = {"all", "omniroute"}


def load_services(path: Path = CONFIG) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("services"), list):
        raise ValueError("private service port configuration has an unsupported format")
    services = data["services"]
    ids: set[str] = set()
    wireguard_ports: set[int] = set()
    for service in services:
        if not isinstance(service, dict):
            raise ValueError("private service entry must be an object")
        service_id = service.get("id")
        if not isinstance(service_id, str) or not service_id or service_id in ids:
            raise ValueError("private service ids must be unique non-empty strings")
        ids.add(service_id)
        if type(service.get("relay")) is not bool or service.get("ssh_group") not in SSH_GROUPS:
            raise ValueError(f"invalid relay or SSH group for {service_id}")
        for field in PORT_FIELDS:
            port = service.get(field)
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError(f"invalid {field} for {service_id}")
        if service["wireguard_port"] in wireguard_ports:
            raise ValueError("WireGuard ports must be unique")
        wireguard_ports.add(service["wireguard_port"])
    if "dashboard" not in ids or "dsh" not in ids:
        raise ValueError("dashboard and DSH ports are required")
    return services


def service_port(service_id: str, field: str = "backend_port", path: Path = CONFIG) -> int:
    if field not in PORT_FIELDS:
        raise ValueError("unsupported service port field")
    for service in load_services(path):
        if service["id"] == service_id:
            return service[field]
    raise ValueError(f"unknown private service: {service_id}")


def relay_pairs(path: Path = CONFIG) -> tuple[tuple[int, int], ...]:
    return tuple(
        (item["wireguard_port"], item["backend_port"])
        for item in load_services(path) if item["relay"]
    )


def wireguard_ports(path: Path = CONFIG) -> tuple[int, ...]:
    return tuple(item["wireguard_port"] for item in load_services(path))


def ssh_forwards(mode: str = "all", dashboard_port: int | None = None, path: Path = CONFIG) -> tuple[tuple[int, int], ...]:
    if mode not in SSH_GROUPS:
        raise ValueError("unsupported SSH tunnel group")
    services = [item for item in load_services(path) if item["ssh_group"] == mode or mode == "all"]
    return tuple(
        (dashboard_port if dashboard_port is not None and item["id"] == "dashboard" else item["wireguard_port"], item["backend_port"])
        for item in services
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", nargs=2, metavar=("SERVICE", "FIELD"), help="print a configured port")
    parser.add_argument("--ssh-forwards", choices=sorted(SSH_GROUPS))
    parser.add_argument("--dashboard-port", type=int)
    parser.add_argument("--wireguard-ports", action="store_true")
    args = parser.parse_args()
    if args.port:
        print(service_port(*args.port))
    elif args.ssh_forwards:
        for local, remote in ssh_forwards(args.ssh_forwards, args.dashboard_port):
            print(f"{local}:{remote}")
    elif args.wireguard_ports:
        print(" ".join(map(str, wireguard_ports())))
    else:
        parser.error("choose --port, --ssh-forwards, or --wireguard-ports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
