#!/usr/bin/env python3
"""Encrypted WireGuard acceptance through a temporary in-memory runtime peer.

Run explicitly as root on the authorized Debian host:
  vpn.py --runtime-fixture [--manifest /path/to/deploy/private-services.json]

Never reads an existing private key or persistent WireGuard configuration.
The client key exists only in process memory and wg setconf stdin. Cleanup removes
the temporary peer/interface/network namespace, including on failed assertions.
"""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time


class FixtureError(Exception):
    pass


SERVER_INTERFACE = "wg0"
CLIENT_IP = "10.8.0.254"
SERVER_IP = "10.8.0.1"
MAX_RUNTIME = 180
MAX_HTTP_BYTES = 2 * 1024 * 1024
TCP_PROBE = (
    "import json,socket,sys,time;"
    "start=time.monotonic();s=socket.socket();s.settimeout(2);"
    "code=s.connect_ex((sys.argv[1],int(sys.argv[2])));s.close();"
    "print(json.dumps({'connected':code==0,'connect_ms':"
    "round((time.monotonic()-start)*1000,2)}))"
)


def system_command(name):
    for directory in ("/usr/bin", "/usr/sbin", "/bin", "/sbin"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise FixtureError("Required system command unavailable: " + name)


def public_key(value):
    try:
        text = value.decode("ascii").strip()
        if len(base64.b64decode(text, validate=True)) != 32:
            raise ValueError()
        return text
    except (UnicodeError, ValueError):
        raise FixtureError("WireGuard returned an invalid key") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-fixture", action="store_true",
                        help="Authorize one temporary runtime peer and bounded network namespace")
    parser.add_argument("--transport-only", action="store_true", help="Baseline transport only; does not close the release large-asset gate")
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).resolve().parents[2] / "deploy/private-services.json")
    args = parser.parse_args()
    if not args.runtime_fixture or sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Requires Linux root and explicit --runtime-fixture")
    try:
        manifest = json.loads(args.manifest.read_text())
    except (OSError, ValueError):
        raise SystemExit("Declared private-service manifest is unavailable") from None
    services = manifest.get("services", [])
    if manifest.get("version") != 1 or len(services) != 9:
        raise SystemExit("Expected the nine declared version-1 private services")
    ports = []
    identifiers = []
    for service in services:
        identifier = service.get("id")
        port = service.get("wireguard_port")
        if (not isinstance(identifier, str) or not identifier
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in identifier)
                or type(port) is not int or not 1 <= port <= 65535):
            raise SystemExit("Invalid declared private service")
        identifiers.append(identifier)
        ports.append(port)
    if len(set(ports)) != 9 or len(set(identifiers)) != 9 or "dashboard" not in identifiers:
        raise SystemExit("Declared service identities and WireGuard ports must be distinct")

    wg = system_command("wg")
    ip = system_command("ip")
    curl = system_command("curl")
    python = system_command("python3")
    namespace = "h07p-vpn-" + secrets.token_hex(4)
    interface = "h07pv" + secrets.token_hex(4)
    started = time.monotonic()
    deadline = started + MAX_RUNTIME
    created_namespace = False
    reserved_interface = False
    reserved_peer = False
    moved_interface = False
    client_public = ""
    private = b""
    config = b""
    baseline = None
    checks = []
    cleanup_errors = []
    failure = None
    handshake = False
    large_transfer = None

    def interrupted(_number, _frame):
        raise FixtureError("Interrupted; temporary runtime cleanup requested")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)

    def run(command, step, data=None, timeout=8, cleanup=False, accepted=(0,)):
        budget = timeout if cleanup else min(timeout, max(0, deadline - time.monotonic()))
        if budget <= 0:
            raise FixtureError("Runtime budget exhausted")
        try:
            result = subprocess.run(command, input=data, capture_output=True,
                                    timeout=budget, check=False)
        except subprocess.TimeoutExpired:
            raise FixtureError(step + " exceeded its time budget") from None
        except OSError:
            raise FixtureError(step + " could not start") from None
        if result.returncode not in accepted:
            # Never include stderr: wg errors may quote a malformed config line.
            raise FixtureError(step + " failed (exit " + str(result.returncode) + ")")
        return result

    def allowed_peers(cleanup=False):
        result = run([wg, "show", SERVER_INTERFACE, "allowed-ips"],
                     "Read public peer routes", cleanup=cleanup)
        peers = {}
        try:
            for line in result.stdout.decode("ascii").splitlines():
                columns = line.split()
                if not columns:
                    continue
                key = public_key(columns[0].encode("ascii"))
                networks = []
                for word in columns[1:]:
                    for item in word.split(","):
                        if item and item != "(none)":
                            networks.append(ipaddress.ip_network(item, strict=False))
                peers[key] = tuple(networks)
        except (UnicodeError, ValueError):
            raise FixtureError("Invalid public WireGuard peer routes") from None
        return peers

    def namespace_command(command, step, **options):
        return run([ip, "netns", "exec", namespace, *command], step, **options)

    def latest_handshake(command, peer):
        result = run(command, "Read public handshake timestamp")
        for line in result.stdout.decode("ascii").splitlines():
            columns = line.split()
            if len(columns) == 2 and columns[0] == peer:
                return int(columns[1]) > 0
        return False

    try:
        baseline = allowed_peers()
        address = ipaddress.ip_address(CLIENT_IP)
        if any(address.version == route.version and address in route
               for routes in baseline.values() for route in routes):
            raise FixtureError("Temporary client address overlaps an existing peer route")
        server_public = public_key(run(
            [wg, "show", SERVER_INTERFACE, "public-key"],
            "Read server public key").stdout)
        try:
            listen_port = int(run(
                [wg, "show", SERVER_INTERFACE, "listen-port"],
                "Read server public listen port").stdout)
        except ValueError:
            raise FixtureError("Invalid WireGuard listen port") from None
        if not 1 <= listen_port <= 65535:
            raise FixtureError("WireGuard has no active listen port")
        namespaces = run([ip, "netns", "list"], "Inspect namespace names").stdout.decode()
        if namespace in {line.split()[0] for line in namespaces.splitlines() if line.split()}:
            raise FixtureError("Temporary namespace name collision")
        result = run([ip, "link", "show", "dev", interface], "Reserve temporary interface",
                     accepted=(0, 1))
        if result.returncode == 0:
            raise FixtureError("Temporary interface name collision")
        private = run([wg, "genkey"], "Generate temporary client key").stdout.strip()
        # Validate without printing the key; public_key is also a 32-byte key validator.
        public_key(private)
        client_public = public_key(run(
            [wg, "pubkey"], "Derive temporary client public key",
            data=private + b"\n").stdout)
        if client_public in baseline:
            raise FixtureError("Temporary public-key collision")

        run([ip, "netns", "add", namespace], "Create bounded client namespace")
        created_namespace = True
        reserved_interface = True
        # Creating before moving preserves the UDP socket's root network namespace.
        run([ip, "link", "add", "dev", interface, "type", "wireguard"],
            "Create WireGuard interface in root network namespace")
        config = (
            b"[Interface]\nPrivateKey = " + private
            + b"\n[Peer]\nPublicKey = " + server_public.encode("ascii")
            + b"\nEndpoint = 127.0.0.1:" + str(listen_port).encode("ascii")
            + b"\nAllowedIPs = 10.8.0.1/32\nPersistentKeepalive = 1\n"
        )
        run([wg, "setconf", interface, "/dev/stdin"],
            "Configure in-memory WireGuard client", data=config)
        private = b""
        config = b""
        reserved_peer = True
        run([wg, "set", SERVER_INTERFACE, "peer", client_public,
             "allowed-ips", CLIENT_IP + "/32"],
            "Add temporary runtime-only server peer")
        run([ip, "link", "set", "dev", interface, "netns", namespace],
            "Move client WireGuard interface into bounded namespace")
        moved_interface = True
        run([ip, "-n", namespace, "link", "set", "lo", "up"], "Enable namespace loopback")
        run([ip, "-n", namespace, "address", "add", CLIENT_IP + "/32", "dev", interface],
            "Assign temporary client address")
        run([ip, "-n", namespace, "link", "set", "dev", interface, "mtu", "1280", "up"],
            "Enable bounded-MTU client interface")
        run([ip, "-n", namespace, "route", "add", SERVER_IP + "/32",
             "dev", interface, "src", CLIENT_IP], "Route only the server tunnel address")
        routes = json.loads(run([ip, "-n", namespace, "-j", "route", "get", SERVER_IP],
                                "Verify client route").stdout)
        if not routes or routes[0].get("dev") != interface:
            raise FixtureError("Client route does not use the WireGuard interface")
        dashboard_port = ports[identifiers.index("dashboard")]
        namespace_command([python, "-c", TCP_PROBE, SERVER_IP, str(dashboard_port)],
                          "Trigger encrypted client traffic", timeout=4)
        for _ in range(30):
            client_ok = latest_handshake(
                [ip, "netns", "exec", namespace, wg, "show", interface, "latest-handshakes"],
                server_public)
            server_ok = latest_handshake(
                [wg, "show", SERVER_INTERFACE, "latest-handshakes"], client_public)
            if client_ok and server_ok:
                handshake = True
                break
            time.sleep(.2)
        if not handshake:
            raise FixtureError("Both ends did not confirm an encrypted WireGuard handshake")

        for service in services:
            port = service["wireguard_port"]
            tcp = json.loads(namespace_command(
                [python, "-c", TCP_PROBE, SERVER_IP, str(port)],
                "Bounded TCP probe", timeout=4).stdout)
            scheme = "https" if service["id"] == "cockpit" else "http"
            command = [
                curl, "--disable", "--noproxy", "*", "--silent", "--show-error",
                "--connect-timeout", "3", "--max-time", "8",
                "--max-filesize", str(MAX_HTTP_BYTES), "--proto", "=http,https",
                "--output", "/dev/null", "--write-out",
                "%{http_code}\t%{size_download}\t%{time_total}\t%{remote_ip}\t%{content_type}",
            ]
            if scheme == "https":
                command.append("--insecure")
            command.append(scheme + "://" + SERVER_IP + ":" + str(port) + "/")
            result = namespace_command(command, "Bounded HTTP transport probe",
                                       timeout=10, accepted=tuple(range(256)))
            columns = result.stdout.decode("ascii", errors="replace").split("\t", 4)
            if len(columns) != 5:
                raise FixtureError("HTTP transport returned malformed status metadata")
            try:
                status = int(columns[0])
                size = int(float(columns[1]))
                http_ms = round(float(columns[2]) * 1000, 2)
            except ValueError:
                raise FixtureError("HTTP transport returned invalid status metadata") from None
            transport = (tcp["connected"] and 100 <= status <= 599
                         and columns[3] == SERVER_IP and result.returncode in (0, 28, 63))
            html_ok = service["id"] != "dashboard" or (
                result.returncode == 0 and status == 200
                and columns[4].lower().startswith("text/html") and size > 0)
            checks.append({
                "service": service["id"], "port": port, "tcp": tcp["connected"],
                "tcp_ms": tcp["connect_ms"], "http_status": status,
                "http_ms": http_ms, "download_bytes": size,
                "bounded_response": result.returncode in (28, 63),
                "transport_passed": transport,
                "dashboard_html_passed": html_ok if service["id"] == "dashboard" else None,
            })
        if not all(check["transport_passed"] and check["dashboard_html_passed"] is not False
                   for check in checks):
            raise FixtureError("One or more declared services failed encrypted transport acceptance")
        if not args.transport_only:
            asset = namespace_command([curl, "--disable", "--noproxy", "*", "--silent", "--show-error",
                "--connect-timeout", "3", "--max-time", "8", "--max-filesize", str(MAX_HTTP_BYTES),
                "--proto", "=http", "--output", "/dev/null", "--write-out", "%{http_code}\t%{size_download}",
                "http://"+SERVER_IP+":"+str(dashboard_port)+"/product.js"], "Bounded large static transfer",timeout=10,accepted=tuple(range(256)))
            fields=asset.stdout.decode("ascii",errors="replace").split("\t")
            large_transfer={"path":"/product.js","http_status":int(fields[0]) if fields else 0,"bytes":int(float(fields[1])) if len(fields)==2 else 0}
            large_transfer["passed"]=asset.returncode==0 and large_transfer["http_status"]==200 and large_transfer["bytes"]>32768
            if not large_transfer["passed"]:
                raise FixtureError("The complete >32 KiB product asset did not pass encrypted transfer acceptance")
        # Public counters corroborate that the validated peer carried encrypted data.
        transfer = run([wg, "show", SERVER_INTERFACE, "transfer"],
                       "Read temporary peer public transfer counters").stdout.decode("ascii")
        received = transmitted = 0
        for line in transfer.splitlines():
            columns = line.split()
            if len(columns) == 3 and columns[0] == client_public:
                received, transmitted = int(columns[1]), int(columns[2])
        if received <= 0 or transmitted <= 0:
            raise FixtureError("Temporary encrypted peer has no bidirectional transfer evidence")
    except (FixtureError, ValueError, KeyError, IndexError) as error:
        failure = str(error) if isinstance(error, FixtureError) else "Fixture metadata validation failed"
    except KeyboardInterrupt:
        failure = "Interrupted; temporary resources were cleaned up"
    finally:
        private = b""
        config = b""
        if reserved_peer:
            try:
                run([wg, "set", SERVER_INTERFACE, "peer", client_public, "remove"],
                    "Remove temporary runtime server peer", cleanup=True)
            except FixtureError as error:
                cleanup_errors.append(str(error))
        if reserved_interface:
            try:
                command = ([ip, "-n", namespace, "link", "delete", "dev", interface]
                           if moved_interface else [ip, "link", "delete", "dev", interface])
                run(command, "Remove temporary client interface", cleanup=True)
            except FixtureError as error:
                cleanup_errors.append(str(error))
        if created_namespace:
            try:
                run([ip, "netns", "delete", namespace],
                    "Remove bounded client namespace", cleanup=True)
            except FixtureError as error:
                cleanup_errors.append(str(error))
        if baseline is not None:
            try:
                remaining = allowed_peers(cleanup=True)
                if client_public and client_public in remaining:
                    raise FixtureError("Temporary server peer remains after cleanup")
                if any(remaining.get(peer) != routes for peer, routes in baseline.items()):
                    raise FixtureError("An original peer route changed during the acceptance run")
                namespaces = run([ip, "netns", "list"], "Verify namespace cleanup",
                                 cleanup=True).stdout.decode()
                if namespace in {line.split()[0] for line in namespaces.splitlines() if line.split()}:
                    raise FixtureError("Temporary network namespace remains")
            except FixtureError as error:
                cleanup_errors.append(str(error))
    report = {
        "result": ("transport_passed" if args.transport_only else "passed") if failure is None and not cleanup_errors else "failed",
        "large_transfer":large_transfer, "transport_only":args.transport_only,
        "encrypted_handshake": handshake, "services": checks,
        "cleanup_complete": not cleanup_errors,
        "runtime_seconds": round(time.monotonic() - started, 2),
        "persistent_configuration_changed": False,
        "authentication_tested": False,
    }
    if failure:
        report["error"] = failure
    if cleanup_errors:
        report["cleanup_errors"] = cleanup_errors
    print(json.dumps(report))
    return 0 if report["result"] in ("passed","transport_passed") else 1


if __name__ == "__main__":
    sys.exit(main())
