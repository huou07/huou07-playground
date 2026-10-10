#!/usr/bin/python3
"""Owner-run, narrowly scoped retirement of the old test application services.

This script never installs apps, touches the dashboard/VPN/Docker, or runs from
the agent. `retire` is reversible. `finalize --accept-data-loss` removes only
the listed playground-managed app accounts and paths after owner acceptance.
"""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_UNITS = {
    "huou07-dsh.service": ("root", "DeepSeek Harness private agent workspace"),
    "huou07-opencode-web.service": ("huou07-opencode", "huou07 OpenCode web workspace"),
    "huou07-litellm.service": ("huou07-litellm", "huou07 LiteLLM gateway"),
    "huou07-litellm-db.service": ("huou07-litellm", "huou07 LiteLLM PostgreSQL database"),
    "huou07-omniroute.service": ("huou07-omniroute", "OmniRoute AI gateway"),
}
SERVICE_USERS = {
    "huou07-dsh": "/var/lib/huou07-dsh",
    "huou07-opencode": "/var/lib/huou07-opencode",
    "huou07-litellm": "/var/lib/huou07-litellm",
    "huou07-omniroute": "/var/lib/huou07-omniroute",
}
OLD_PATHS = (
    "/opt/huou07-dsh",
    "/srv/huou07-dsh-workspaces",
    "/srv/huou07-opencode-workspaces",
    "/etc/huou07-litellm",
    "/etc/huou07-omniroute",
    "/usr/local/libexec/huou07-dsh",
    "/usr/local/libexec/huou07-opencode",
    "/usr/local/libexec/huou07-litellm",
    "/usr/local/libexec/huou07-omniroute",
)
OLD_FILES = (
    "/etc/huou07-playground/opencode-web.env",
    "/etc/systemd/system/huou07-dsh.service",
    "/etc/systemd/system/huou07-opencode-web.service",
    "/etc/systemd/system/huou07-litellm.service",
    "/etc/systemd/system/huou07-litellm-db.service",
    "/etc/systemd/system/huou07-omniroute.service",
)
STATE_FILE = Path("/var/lib/huou07-playground/clean-app-reinstall-state.json")
TMPFILES_RULE = Path("/etc/tmpfiles.d/huou07-dsh-link.conf")
DSH_URL_FILE = Path("/run/huou07-dsh-link/url")
NEW_USER_UNITS = ("dsh.service", "opencode-web.service")
NEW_QUADLETS = (
    "litellm.pod", "litellm-postgres.volume", "litellm-db.container", "litellm.container",
    "omniroute.pod", "omniroute-redis.volume", "omniroute-redis.container", "omniroute.container",
)


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check)


def require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run this owner-reviewed step with sudo from the repository checkout.")


def systemd_property(unit: str, prop: str) -> str:
    return run(["systemctl", "show", "--property=" + prop, "--value", unit]).stdout.strip()


def validate_old_installation(*, must_be_active: bool) -> None:
    if run(["loginctl", "show-user", "huou07", "--property=Linger", "--value"], check=False).stdout.strip() != "yes":
        raise RuntimeError("The huou07 user manager does not have lingering enabled; user services would not persist after logout/reboot.")
    if not Path("/var/lib/huou07-playground/apps.json").is_file():
        raise RuntimeError("Dashboard registry is missing; refusing to assume this is the intended host.")
    if systemd_property("huou07-playground.service", "ActiveState") != "active":
        raise RuntimeError("The dashboard is not active; refusing application retirement.")
    if run(["systemctl", "is-active", "huou07-wg-easy.service"], check=False).returncode != 0:
        raise RuntimeError("The existing wg-easy service is not active; refusing application retirement.")
    if run(["ip", "link", "show", "dev", "wg0"], check=False).returncode != 0:
        raise RuntimeError("WireGuard interface wg0 is not present; refusing application retirement.")
    if not run(["ss", "-H", "-lun", "sport", "=", ":3478"], check=False).stdout.strip():
        raise RuntimeError("The verified WireGuard UDP 3478 listener is missing; refusing application retirement.")
    if run(["systemctl", "is-active", "docker.service"], check=False).returncode != 0:
        raise RuntimeError("The existing rootful Docker daemon is not active; refusing application retirement.")
    for unit, (expected_user, expected_description) in APP_UNITS.items():
        path = Path("/etc/systemd/system") / unit
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Expected app unit is missing or not a regular file: {path}")
        if systemd_property(unit, "FragmentPath") != str(path):
            raise RuntimeError(f"{unit} is not the local playground unit; refusing to change it.")
        if systemd_property(unit, "Description") != expected_description:
            raise RuntimeError(f"Unexpected description in {unit}; refusing to change it.")
        if systemd_property(unit, "User") != expected_user:
            raise RuntimeError(f"Unexpected service identity in {unit}; refusing to change it.")
        if list(path.parent.glob(unit + ".d/*.conf")):
            raise RuntimeError(f"Unit drop-ins exist for {unit}; review them before retirement.")
        active = systemd_property(unit, "ActiveState") == "active"
        if must_be_active and not active:
            raise RuntimeError(f"Expected currently running app unit: {unit}")
    for account, expected_home in SERVICE_USERS.items():
        try:
            info = pwd.getpwnam(account)
        except KeyError as exc:
            raise RuntimeError(f"Expected old app service account is missing: {account}") from exc
        if info.pw_uid >= 1000 or info.pw_dir != expected_home or info.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin"}:
            raise RuntimeError(f"Account {account} does not match its verified system-account path; refusing cleanup.")
        if Path(info.pw_dir).is_symlink():
            raise RuntimeError(f"Service account home is a symlink; refusing cleanup: {info.pw_dir}")
        try:
            primary_group = grp.getgrnam(account)
        except KeyError as exc:
            raise RuntimeError(f"Expected primary group is missing: {account}") from exc
        if primary_group.gr_gid != info.pw_gid or set(primary_group.gr_mem) - {account}:
            raise RuntimeError(f"The old service group is shared; refusing cleanup: {account}")


def read_state() -> dict:
    if not STATE_FILE.is_file() or STATE_FILE.is_symlink():
        raise RuntimeError("No valid retirement checkpoint exists. Run preflight, then retire.")
    return json.loads(STATE_FILE.read_text())


def preflight() -> None:
    validate_old_installation(must_be_active=True)
    if STATE_FILE.exists():
        raise RuntimeError(f"A prior retirement checkpoint exists: {STATE_FILE}")
    expected_rule = "d /run/huou07-dsh-link 2750 huou07 huou07-dsh-link -\n"
    if TMPFILES_RULE.exists() and TMPFILES_RULE.read_text() != expected_rule:
        raise RuntimeError(f"An unrelated tmpfiles rule already exists: {TMPFILES_RULE}")
    if shutil.which("systemd-tmpfiles") is None:
        raise RuntimeError("systemd-tmpfiles is not installed.")
    print("Read-only preflight passed. The script will stop only these five application units:")
    for unit in APP_UNITS:
        print(f"  {unit}")
    print("The dashboard, WireGuard, Docker, Cockpit, and all other containers/services are outside scope.")
    print("Existing app directories and service accounts remain intact until finalize.")
    print("WARNING: the owner's existing sudo and Docker access are retained and can grant root-equivalent power to processes running as huou07; this is informational and does not block the clean install.")


def retire() -> None:
    preflight()
    enabled = {}
    active = {}
    for unit in APP_UNITS:
        enabled[unit] = systemd_property(unit, "UnitFileState") in {"enabled", "enabled-runtime"}
        active[unit] = systemd_property(unit, "ActiveState") == "active"
    state = {"created": datetime.now(timezone.utc).isoformat(), "enabled": enabled, "active": active}
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
    os.chmod(STATE_FILE, 0o600)
    # Reverse the app dependency order; no shared infrastructure is stopped.
    for unit in ("huou07-litellm.service", "huou07-litellm-db.service", "huou07-omniroute.service", "huou07-opencode-web.service", "huou07-dsh.service"):
        if active[unit]:
            run(["systemctl", "stop", unit])
        if enabled[unit]:
            run(["systemctl", "disable", unit])
    expected_rule = "d /run/huou07-dsh-link 2750 huou07 huou07-dsh-link -\n"
    if not TMPFILES_RULE.exists():
        TMPFILES_RULE.write_text(expected_rule)
        os.chmod(TMPFILES_RULE, 0o644)
    run(["systemd-tmpfiles", "--create", str(TMPFILES_RULE)])
    run(["install", "-d", "-o", "huou07", "-g", "huou07-dsh-link", "-m", "2750", "/run/huou07-dsh-link"])
    print("Old app units are stopped and disabled. Their data/accounts remain available for rollback.")
    print("Next: as huou07, run deploy/install-user-apps.sh install; then verify the apps in the browser.")


def rollback() -> None:
    state = read_state()
    validate_old_installation(must_be_active=False)
    owner_home = Path(pwd.getpwnam("huou07").pw_dir)
    hold = owner_home / ".local/share/huou07-playground/rollback/containers-systemd"
    quadlet_dir = owner_home / ".config/containers/systemd"
    if hold.exists() or hold.is_symlink():
        raise RuntimeError(f"A rollback holding directory already exists; inspect it: {hold}")
    for name in NEW_QUADLETS:
        if (quadlet_dir / name).is_symlink():
            raise RuntimeError(f"Refusing to move a symlinked Quadlet: {quadlet_dir / name}")
    # Stop only the new user apps. Move Quadlet definitions aside so they do
    # not come back at the next boot and collide with restored system units.
    for unit in (*NEW_USER_UNITS, "litellm-pod.service", "litellm-postgres-volume.service", "litellm-db.service", "litellm.service",
                 "omniroute-pod.service", "omniroute-redis-volume.service", "omniroute-redis.service", "omniroute.service"):
        run(["systemctl", "--machine=huou07@", "--user", "stop", unit], check=False)
    for unit in (*NEW_USER_UNITS, "litellm-pod.service", "litellm-postgres-volume.service", "litellm-db.service", "litellm.service",
                 "omniroute-pod.service", "omniroute-redis-volume.service", "omniroute-redis.service", "omniroute.service"):
        run(["systemctl", "--machine=huou07@", "--user", "disable", unit], check=False)
    if any((quadlet_dir / name).exists() for name in NEW_QUADLETS):
        hold.mkdir(parents=True, mode=0o700)
        for name in NEW_QUADLETS:
            source = quadlet_dir / name
            if source.exists():
                shutil.move(str(source), str(hold / name))
        run(["systemctl", "--machine=huou07@", "--user", "daemon-reload"], check=False)
    for unit in APP_UNITS:
        if state["enabled"].get(unit):
            run(["systemctl", "enable", unit])
        else:
            run(["systemctl", "disable", unit], check=False)
    for unit in APP_UNITS:
        if state["active"].get(unit):
            run(["systemctl", "start", unit])
    STATE_FILE.unlink()
    print("Previous application services were restored. No application data was deleted.")
    if hold.exists():
        print(f"The new Quadlet definitions are preserved at {hold}; run the user installer's resume action to retry later.")


def verify_user_services() -> None:
    units = (
        "dsh.service", "opencode-web.service", "litellm-pod.service", "litellm-postgres-volume.service",
        "litellm-db.service", "litellm.service", "omniroute-pod.service", "omniroute-redis-volume.service",
        "omniroute-redis.service", "omniroute.service",
    )
    for unit in units:
        result = run(["systemctl", "--machine=huou07@", "--user", "is-active", unit], check=False)
        if result.returncode or result.stdout.strip() != "active":
            raise RuntimeError(f"New owner user service is not active: {unit}")
    for port in (3080, 4096, 4000, 20128, 20129, 20132):
        result = run(["/usr/bin/python3", "-c", "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',int(sys.argv[1]))); s.close()", str(port)], check=False)
        if result.returncode:
            raise RuntimeError(f"Expected new loopback service is unavailable on port {port}.")
    try:
        dsh_link = DSH_URL_FILE.read_text().strip()
        dsh_stat = DSH_URL_FILE.stat()
        link_group = grp.getgrnam("huou07-dsh-link")
    except (OSError, KeyError) as exc:
        raise RuntimeError("The private DSH dashboard login link is unavailable.") from exc
    if (not re.fullmatch(r"/\?token=[A-Za-z0-9_-]{32,128}", dsh_link)
            or dsh_stat.st_uid != pwd.getpwnam("huou07").pw_uid
            or dsh_stat.st_gid != link_group.gr_gid
            or not (dsh_stat.st_mode & 0o040)):
        raise RuntimeError("The DSH dashboard login link has unexpected ownership or permissions.")
    for endpoint in ("http://127.0.0.1:4000/health/readiness", "http://127.0.0.1:20128/healthz"):
        result = run(["curl", "--fail", "--silent", "--max-time", "5", endpoint], check=False)
        if result.returncode:
            raise RuntimeError(f"New application health check failed: {endpoint}")
    for name in SERVICE_USERS:
        info = pwd.getpwnam(name)
        if run(["pgrep", "-u", str(info.pw_uid)], check=False).returncode == 0:
            raise RuntimeError(f"Old service account still has a running process: {name}")
    if systemd_property("huou07-playground.service", "ActiveState") != "active":
        raise RuntimeError("Dashboard health changed; refusing cleanup.")
    if run(["systemctl", "is-active", "huou07-wg-easy.service"], check=False).returncode:
        raise RuntimeError("WireGuard health changed; refusing cleanup.")
    if run(["ip", "link", "show", "dev", "wg0"], check=False).returncode:
        raise RuntimeError("WireGuard interface wg0 is missing; refusing cleanup.")
    if not run(["ss", "-H", "-lun", "sport", "=", ":3478"], check=False).stdout.strip():
        raise RuntimeError("WireGuard UDP 3478 listener is missing; refusing cleanup.")
    if run(["systemctl", "is-active", "docker.service"], check=False).returncode:
        raise RuntimeError("Docker health changed; refusing cleanup.")


def remove_exact(path_text: str) -> None:
    path = Path(path_text)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        raise RuntimeError(f"Refusing to follow a symlink cleanup target: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def remove_subid_mapping(path_text: str, user: str) -> None:
    path = Path(path_text)
    if not path.exists():
        return
    rows = path.read_text().splitlines(keepends=True)
    kept = [row for row in rows if row.split(":", 1)[0] != user]
    if len(kept) == len(rows):
        return
    backup = path.with_name(path.name + ".huou07-playground-backup")
    if backup.exists():
        raise RuntimeError(f"Subordinate-ID backup already exists; review it before cleanup: {backup}")
    shutil.copy2(path, backup)
    temp = path.with_name(path.name + ".huou07-playground-tmp")
    with temp.open("x") as stream:
        stream.writelines(kept)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temp, path.stat().st_mode & 0o777)
    os.replace(temp, path)


def finalize(accepted: bool) -> None:
    if not accepted:
        raise RuntimeError("Final cleanup is destructive. Repeat with --accept-data-loss after browser acceptance.")
    read_state()
    validate_old_installation(must_be_active=False)
    verify_user_services()
    for path_text in OLD_PATHS + OLD_FILES:
        path = Path(path_text)
        if path.is_symlink():
            raise RuntimeError(f"Refusing cleanup because a listed target is a symlink: {path}")
    for user in SERVICE_USERS:
        for id_file in (Path("/etc/subuid"), Path("/etc/subgid")):
            backup = id_file.with_name(id_file.name + ".huou07-playground-backup")
            if backup.exists() and any(row.split(":", 1)[0] == user for row in id_file.read_text().splitlines()):
                raise RuntimeError(f"Subordinate-ID backup already exists; review it before cleanup: {backup}")
    # Add health probes only after every cleanup target has passed validation,
    # but before deleting the old services so a registry write failure is safe.
    # Existing custom URLs and probes are kept by the dashboard registry helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from register_app import register_default_app

    dashboard_apps = (
        ("DeepSeek Harness", "http://127.0.0.1:3080/", "Coding Agents", "Private DSH Web sessions.", "http://127.0.0.1:3080/", None),
        ("OpenCode Web", "http://127.0.0.1:14096/", "Coding Agents", "Private OpenCode Web using the owner CLI configuration.", "http://127.0.0.1:4096/global/health", "http://127.0.0.1:14096/"),
        ("LiteLLM Gateway", "http://127.0.0.1:4000/ui", "AI Gateway", "Private LiteLLM management UI.", "http://127.0.0.1:4000/health/readiness", "http://127.0.0.1:4000/ui"),
        ("OmniRoute", "http://127.0.0.1:20128/", "AI Gateway", "Private OmniRoute dashboard.", "http://127.0.0.1:20128/healthz", "http://127.0.0.1:20128/"),
    )
    for name, url, category, description, health_url, management_url in dashboard_apps:
        register_default_app({
            "name": name, "url": url, "category": category, "description": description,
            "health_url": health_url, "health_method": "GET", "management_url": management_url,
        }, migrate_health_from=(None,))
    # All targets are fixed, app-specific paths; no glob, home-wide, Docker, or /var/lib sweep.
    for user in SERVICE_USERS:
        try:
            info = pwd.getpwnam(user)
        except KeyError:
            continue
        if info.pw_dir != SERVICE_USERS[user] or Path(info.pw_dir).is_symlink():
            raise RuntimeError(f"Unexpected account home encountered for {user}; refusing removal.")
        run(["userdel", "--remove", user])
        group = run(["getent", "group", user], check=False)
        if group.returncode == 0:
            run(["groupdel", user], check=False)
        for id_file in ("/etc/subuid", "/etc/subgid"):
            remove_subid_mapping(id_file, user)
    for path in OLD_PATHS + OLD_FILES:
        remove_exact(path)
    for unit in APP_UNITS:
        unit_file = Path("/etc/systemd/system") / unit
        if unit_file.exists():
            unit_file.unlink()
    run(["systemctl", "daemon-reload"])
    STATE_FILE.unlink()
    print("Old test-only app accounts, units, and exact app state paths were removed.")
    print("Dashboard, WireGuard, rootful Docker, Cockpit, AN3, AdGuard Home, and unrelated data were not touched.")


def main() -> None:
    require_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "retire", "rollback", "finalize"))
    parser.add_argument("--accept-data-loss", action="store_true")
    args = parser.parse_args()
    try:
        {"preflight": preflight, "retire": retire, "rollback": rollback,
         "finalize": lambda: finalize(args.accept_data_loss)}[args.action]()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        message = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        raise SystemExit(f"Stopped safely: {message}") from exc


if __name__ == "__main__":
    main()
