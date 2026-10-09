#!/usr/bin/env python3
"""Reconcile only the WireGuard firewall rules recorded as huou07-managed."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.private_services import load_services


STATE_DIR = Path("/etc/huou07-playground")
TCP_STATE = STATE_DIR / "wg-private-web-access.ports"
UDP_STATE = STATE_DIR / "wg-udp-access.rules"
UFW = "/usr/sbin/ufw"
IP = "/usr/sbin/ip"
WG = "/usr/bin/wg"
TCP_COMMENT = "huou07 private app access"
UDP_COMMENT = "huou07 WireGuard endpoint"


def command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)


def validate_port(value: str | int) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid port")
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid port") from error
    if not 1 <= port <= 65535 or str(port) != str(value):
        raise ValueError("invalid port")
    return port


def parse_status_rules(status: str) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    for line in status.splitlines():
        left, _, comment = line.partition("#")
        fields = left.split()
        if len(fields) > 1 and fields[1] == "(v6)":
            fields.pop(1)
        if len(fields) < 4:
            continue
        rule = fields[0]
        match = re.fullmatch(r"([0-9]{1,5})/(tcp|udp)", rule)
        if not match or fields[1] != "on" or fields[3] != "ALLOW":
            continue
        try:
            validate_port(match.group(1))
        except ValueError:
            continue
        interface = fields[2]
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", interface):
            continue
        rules.append({"port": match.group(1), "protocol": match.group(2), "interface": interface, "comment": comment.strip()})
    return rules


class PrivateFirewall:
    def __init__(self, state_dir: Path = STATE_DIR, runner=command, ufw: str = UFW, services: list[dict] | None = None):
        self.state_dir = state_dir
        self.runner = runner
        self.ufw = ufw
        self.services = load_services() if services is None else services

    def status(self) -> str:
        result = self.runner([self.ufw, "status"])
        if result.returncode != 0:
            raise RuntimeError("Could not read UFW status.")
        return result.stdout

    def active(self) -> bool:
        return self.status().splitlines()[0:1] == ["Status: active"]

    @staticmethod
    def matches(rules: list[dict[str, str]], port: int, protocol: str, interface: str, comment: str | None = None) -> bool:
        return any(
            rule["port"] == str(port) and rule["protocol"] == protocol and rule["interface"] == interface
            and (comment is None or rule["comment"] == comment)
            for rule in rules
        )

    def state_path(self, protocol: str) -> Path:
        return self.state_dir / ("wg-private-web-access.ports" if protocol == "tcp" else "wg-udp-access.rules")

    def read_state(self, protocol: str) -> list[tuple[str, int]]:
        path = self.state_path(protocol)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Firewall state is not a regular file.")
        if not path.exists():
            return []
        entries: list[tuple[str, int]] = []
        for line in path.read_text().splitlines():
            fields = line.split()
            if protocol == "tcp" and len(fields) == 1:
                entries.append(("wg0", validate_port(fields[0])))
            elif protocol == "udp" and len(fields) == 2 and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", fields[0]):
                entries.append((fields[0], validate_port(fields[1])))
            else:
                raise ValueError("Firewall state contains an invalid record.")
        return list(dict.fromkeys(entries))

    def write_state(self, protocol: str, entries: list[tuple[str, int]]) -> None:
        path = self.state_path(protocol)
        self.state_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        if not entries:
            path.unlink(missing_ok=True)
            return
        lines = [str(port) if protocol == "tcp" else f"{interface} {port}" for interface, port in entries]
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=self.state_dir, text=True)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write("\n".join(lines) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def allow(self, port: int, protocol: str, interface: str, comment: str) -> None:
        result = self.runner([self.ufw, "allow", "in", "on", interface, "to", "any", "port", str(port), "proto", protocol, "comment", comment])
        if result.returncode != 0:
            raise RuntimeError(f"UFW could not add the {protocol} rule for port {port}.")

    def delete_owned(self, port: int, protocol: str, interface: str, comment: str) -> bool:
        rules = parse_status_rules(self.status())
        if not self.matches(rules, port, protocol, interface, comment):
            return False
        for _ in range(4):
            rules = parse_status_rules(self.status())
            if not self.matches(rules, port, protocol, interface, comment):
                return True
            result = self.runner([self.ufw, "--force", "delete", "allow", "in", "on", interface, "to", "any", "port", str(port), "proto", protocol, "comment", comment])
            if result.returncode != 0:
                return False
        return not self.matches(parse_status_rules(self.status()), port, protocol, interface, comment)

    def apply_tcp(self) -> str:
        if not self.active():
            return "UFW is inactive; no private access rules changed."
        self.state_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        desired = list(dict.fromkeys(("wg0", item["wireguard_port"]) for item in self.services))
        tracked = self.read_state("tcp")
        rules = parse_status_rules(self.status())
        added: list[tuple[str, int]] = []
        for interface, port in desired:
            if not self.matches(rules, port, "tcp", interface):
                self.allow(port, "tcp", interface, TCP_COMMENT)
                added.append((interface, port))
                rules = parse_status_rules(self.status())
                if not self.matches(rules, port, "tcp", interface, TCP_COMMENT):
                    for added_interface, added_port in added:
                        self.delete_owned(added_port, "tcp", added_interface, TCP_COMMENT)
                    raise RuntimeError(f"UFW did not confirm the private TCP rule for port {port}.")
        tracked = list(dict.fromkeys(tracked + added))
        self.write_state("tcp", tracked)

        retained: list[tuple[str, int]] = []
        desired_set = set(desired)
        for interface, port in tracked:
            if (interface, port) in desired_set:
                if self.matches(parse_status_rules(self.status()), port, "tcp", interface, TCP_COMMENT):
                    retained.append((interface, port))
            elif self.matches(parse_status_rules(self.status()), port, "tcp", interface, TCP_COMMENT):
                if not self.delete_owned(port, "tcp", interface, TCP_COMMENT):
                    retained.append((interface, port))
            elif self.matches(parse_status_rules(self.status()), port, "tcp", interface):
                retained.append((interface, port))
        self.write_state("tcp", retained)
        return "Verified all configured TCP application ports on wg0; preserved unrecorded owner rules."

    def apply_udp(self, listen_port: int, interface: str) -> str:
        listen_port = validate_port(listen_port)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", interface):
            raise ValueError("Default-route interface is invalid.")
        if not self.active():
            return "UFW is inactive; no WireGuard UDP rule changed."
        self.state_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        desired = (interface, listen_port)
        tracked = self.read_state("udp")
        rules = parse_status_rules(self.status())
        added = False
        if not self.matches(rules, listen_port, "udp", interface):
            self.allow(listen_port, "udp", interface, UDP_COMMENT)
            added = True
            rules = parse_status_rules(self.status())
            if not self.matches(rules, listen_port, "udp", interface, UDP_COMMENT):
                self.delete_owned(listen_port, "udp", interface, UDP_COMMENT)
                raise RuntimeError("UFW did not confirm the active WireGuard listener rule.")
        tracked = list(dict.fromkeys(tracked + ([desired] if added else [])))
        self.write_state("udp", tracked)

        retained: list[tuple[str, int]] = []
        for old_interface, old_port in tracked:
            if (old_interface, old_port) == desired:
                if self.matches(parse_status_rules(self.status()), old_port, "udp", old_interface, UDP_COMMENT):
                    retained.append((old_interface, old_port))
            elif self.matches(parse_status_rules(self.status()), old_port, "udp", old_interface, UDP_COMMENT):
                if not self.delete_owned(old_port, "udp", old_interface, UDP_COMMENT):
                    retained.append((old_interface, old_port))
            elif self.matches(parse_status_rules(self.status()), old_port, "udp", old_interface):
                retained.append((old_interface, old_port))
        self.write_state("udp", retained)
        return "Verified the active WireGuard UDP rule before pruning only obsolete recorded rules."

    def remove(self, protocol: str, active_udp: tuple[int, str] | None = None) -> str:
        if protocol not in {"tcp", "udp"}:
            raise ValueError("unsupported firewall protocol")
        path = self.state_path(protocol)
        entries = self.read_state(protocol)
        if not entries:
            return f"No huou07-managed {protocol.upper()} firewall rules are recorded."
        if protocol == "udp" and active_udp is None:
            raise RuntimeError("Cannot remove recorded WireGuard rules without verifying the active listener.")
        retained: list[tuple[str, int]] = []
        comment = TCP_COMMENT if protocol == "tcp" else UDP_COMMENT
        for interface, port in entries:
            if protocol == "udp" and (port, interface) == active_udp:
                retained.append((interface, port))
                continue
            if not self.delete_owned(port, protocol, interface, comment):
                if self.matches(parse_status_rules(self.status()), port, protocol, interface):
                    retained.append((interface, port))
        self.write_state(protocol, retained)
        return f"Removed only recorded huou07-managed {protocol.upper()} rules; active VPN and unowned rules were preserved."


def active_udp_endpoint(runner=command) -> tuple[int, str] | None:
    port_result = runner([WG, "show", "wg0", "listen-port"])
    if port_result.returncode != 0:
        return None
    try:
        port = validate_port(port_result.stdout.strip())
    except ValueError:
        return None
    route = runner([IP, "-4", "route", "get", "1.1.1.1"])
    if route.returncode != 0:
        return None
    fields = route.stdout.split()
    try:
        interface = fields[fields.index("dev") + 1]
    except (ValueError, IndexError):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", interface):
        return None
    return port, interface


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply-tcp", "apply-udp", "remove-tcp", "remove-udp"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run as root")
    firewall = PrivateFirewall()
    try:
        if args.action == "apply-tcp":
            message = firewall.apply_tcp()
        elif args.action == "apply-udp":
            endpoint = active_udp_endpoint()
            if endpoint is None:
                message = "No valid wg0 UDP listener or default route; no firewall rules changed."
            else:
                message = firewall.apply_udp(*endpoint)
        elif args.action == "remove-tcp":
            message = firewall.remove("tcp")
        else:
            message = firewall.remove("udp", active_udp_endpoint())
        print(message)
        return 0
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
