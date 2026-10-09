#!/bin/sh
set -eu

SERVICE=huou07-omniroute
STATE_DIR=/var/lib/$SERVICE
CONFIG_DIR=/etc/$SERVICE
LIBEXEC_DIR=/usr/local/libexec/$SERVICE
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IMAGE=docker.io/diegosouzapw/omniroute:3.8.51
REDIS_IMAGE=docker.io/library/redis:8.6.5-alpine

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install-omniroute.sh)." >&2
  exit 1
fi
if [ ! -x /usr/bin/podman ] || [ ! -x /usr/bin/slirp4netns ] || [ ! -x /usr/bin/systemctl ] || [ ! -d /run/systemd/system ]; then
  echo "A running systemd installation with Podman and slirp4netns is required." >&2
  exit 1
fi
if [ ! -f /etc/huou07-playground/apps.json ] || [ ! -d /opt/huou07-playground/current ]; then
  echo "Install huou07 playground before the OmniRoute integration." >&2
  exit 1
fi
unit="/etc/systemd/system/$SERVICE.service"
if [ -e "$unit" ] && {
  ! grep -Fqx "Description=huou07 OmniRoute AI gateway" "$unit" ||
  ! grep -Fq -- "--name $SERVICE-app" "$unit" ||
  ! grep -Fq "$IMAGE" "$unit"
}; then
  echo "An unrelated $SERVICE.service unit already exists; refusing to replace it." >&2
  exit 1
fi

if getent passwd "$SERVICE" >/dev/null; then
  account=$(getent passwd "$SERVICE")
  account_uid=$(printf '%s\n' "$account" | cut -d: -f3)
  account_home=$(printf '%s\n' "$account" | cut -d: -f6)
  account_shell=$(printf '%s\n' "$account" | cut -d: -f7)
  if [ "$account_uid" -ge 1000 ] || [ "$account_home" != "$STATE_DIR" ] || [ "$account_shell" != /usr/sbin/nologin ] || ! getent group "$SERVICE" >/dev/null; then
    echo "The existing $SERVICE account does not match the dedicated service account; refusing to reuse it." >&2
    exit 1
  fi
else
  useradd --system --user-group --home-dir "$STATE_DIR" --create-home --shell /usr/sbin/nologin "$SERVICE"
fi

range_start=$(awk -F: '
  { end = $2 + $3; if (end > max) max = end }
  END {
    start = int((max + 65535) / 65536) * 65536
    if (start < 100000) start = 100000
    print start
  }
' /etc/subuid /etc/subgid)
subuid_range=$(awk -F: -v service="$SERVICE" '$1 == service { print $2 ":" $3 }' /etc/subuid)
subgid_range=$(awk -F: -v service="$SERVICE" '$1 == service { print $2 ":" $3 }' /etc/subgid)
if [ -z "$subuid_range" ] && [ -z "$subgid_range" ]; then
  printf '%s:%s:65536\n' "$SERVICE" "$range_start" >> /etc/subuid
  printf '%s:%s:65536\n' "$SERVICE" "$range_start" >> /etc/subgid
elif [ "$subuid_range" != "$subgid_range" ]; then
  echo "The existing $SERVICE subordinate UID/GID ranges do not match; refusing to alter them." >&2
  exit 1
else
  range_count=${subuid_range#*:}
  if [ "${subuid_range%%:*}" -lt 100000 ] || [ "$range_count" -lt 65536 ]; then
    echo "The existing $SERVICE subordinate ID range is too small or reserved." >&2
    exit 1
  fi
fi

install -d -o "$SERVICE" -g "$SERVICE" -m 0750 "$STATE_DIR" "$STATE_DIR/data"
install -d -o root -g root -m 0755 "$CONFIG_DIR" "$LIBEXEC_DIR"
if [ -e "$STATE_DIR/.config" ] && { [ -L "$STATE_DIR/.config" ] || [ ! -d "$STATE_DIR/.config" ]; }; then
  echo "The dedicated OmniRoute config path is not a real directory; refusing to replace it." >&2
  exit 1
fi
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$STATE_DIR/.config"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$STATE_DIR/.config/containers"
containers_config="$STATE_DIR/.config/containers/containers.conf"
if [ -e "$containers_config" ]; then
  if [ -L "$containers_config" ] || ! grep -Eq '^[[:space:]]*default_rootless_network_cmd[[:space:]]*=[[:space:]]*"slirp4netns"$' "$containers_config"; then
    echo "The dedicated OmniRoute account has an incompatible Podman configuration; refusing to replace it." >&2
    exit 1
  fi
  if grep -Eq '^[[:space:]]*cgroup_manager[[:space:]]*=' "$containers_config"; then
    if ! grep -Eq '^[[:space:]]*cgroup_manager[[:space:]]*=[[:space:]]*"cgroupfs"$' "$containers_config"; then
      echo "The dedicated OmniRoute account has an incompatible Podman cgroup manager; refusing to replace it." >&2
      exit 1
    fi
  else
    printf '\n[engine]\ncgroup_manager = "cgroupfs"\n' >> "$containers_config"
  fi
else
  containers_tmp=$(mktemp "$STATE_DIR/.config/containers/.containers.conf.XXXXXX")
  printf '[network]\ndefault_rootless_network_cmd = "slirp4netns"\n\n[engine]\ncgroup_manager = "cgroupfs"\n' > "$containers_tmp"
  chown "$SERVICE:$SERVICE" "$containers_tmp"
  chmod 0600 "$containers_tmp"
  mv "$containers_tmp" "$containers_config"
fi

if [ -e "$CONFIG_DIR/omniroute.env" ] && [ -L "$CONFIG_DIR/omniroute.env" ]; then
  echo "The OmniRoute environment must not be a symbolic link." >&2
  exit 1
fi
if [ ! -e "$CONFIG_DIR/omniroute.env" ]; then
  python3 - "$CONFIG_DIR/omniroute.env" <<'PY'
import os
import secrets
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
values = {
    "JWT_SECRET": secrets.token_hex(32),
    "API_KEY_SECRET": secrets.token_hex(32),
    "OMNIROUTE_WS_BRIDGE_SECRET": secrets.token_hex(32),
    "MACHINE_ID_SALT": secrets.token_hex(32),
    "OMNIROUTE_CLI_SALT": secrets.token_hex(32),
    "INITIAL_PASSWORD": secrets.token_hex(24),
    "REQUIRE_API_KEY": "true",
    "ALLOW_API_KEY_REVEAL": "false",
    "APP_BIND_HOST": "127.0.0.1",
    "DASHBOARD_PORT": "20128",
    "API_PORT": "20129",
    "LIVE_WS_PORT": "20132",
    "DATA_DIR": "/app/data",
    "REDIS_URL": "redis://127.0.0.1:6379",
    "OMNIROUTE_MEMORY_MB": "8192",
    "NODE_ENV": "production",
}
fd, temporary = tempfile.mkstemp(prefix=".omniroute.env.", dir=path.parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
fi
chown root:root "$CONFIG_DIR/omniroute.env"
chmod 0600 "$CONFIG_DIR/omniroute.env"

install -o root -g root -m 0755 "$SOURCE/deploy/omniroute-prepare.sh" "$LIBEXEC_DIR/prepare.sh"
install -o root -g root -m 0755 "$SOURCE/deploy/omniroute-wait-ready.sh" "$LIBEXEC_DIR/wait-ready.sh"
install -o root -g root -m 0755 "$SOURCE/deploy/omniroute-wait-redis.sh" "$LIBEXEC_DIR/wait-redis.sh"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$SERVICE.service" "$unit"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 /run/huou07-omniroute
run_as_omniroute() {
  (cd "$STATE_DIR" && runuser -u "$SERVICE" -- env HOME="$STATE_DIR" XDG_RUNTIME_DIR=/run/huou07-omniroute "$@")
}
run_as_omniroute /usr/bin/podman info >/dev/null
if ! run_as_omniroute /usr/bin/podman image exists "$REDIS_IMAGE"; then
  run_as_omniroute /usr/bin/podman pull "$REDIS_IMAGE"
fi
if ! run_as_omniroute /usr/bin/podman image exists "$IMAGE"; then
  run_as_omniroute /usr/bin/podman pull "$IMAGE"
fi
run_as_omniroute /usr/bin/podman unshare chown -R 1000:1000 "$STATE_DIR/data"
run_as_omniroute /usr/local/libexec/huou07-omniroute/prepare.sh

systemctl daemon-reload
systemctl enable "$SERVICE.service"
systemctl restart "$SERVICE.service"
attempt=0
while [ "$attempt" -lt 320 ]; do
  state=$(systemctl show --property=ActiveState --value "$SERVICE.service")
  if [ "$state" = active ] && /usr/bin/curl --fail --silent --max-time 3 http://127.0.0.1:20128/healthz >/dev/null 2>&1; then
    break
  fi
  if [ "$state" = failed ]; then
    echo "OmniRoute failed to start; inspect its systemd journal." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 1
done
if [ "$attempt" -ge 320 ]; then
  echo "OmniRoute did not become ready on loopback." >&2
  exit 1
fi

PYTHONPATH="$SOURCE" APPS_FILE=/etc/huou07-playground/apps.json python3 - <<'PY'
from web.app import mutate_app_registry, validate_app_entries
import json
from pathlib import Path

path = Path("/etc/huou07-playground/apps.json")
apps = validate_app_entries(json.loads(path.read_text()))
name = "OmniRoute"
app = {
    "name": name,
    "url": "http://127.0.0.1:20128/",
    "description": "Self-hosted free-model gateway. Sign in to add providers and API keys.",
    "category": "AI Gateway",
    "health_url": "http://127.0.0.1:20128/healthz",
    "health_method": "GET",
    "management_url": "http://127.0.0.1:20128/",
}
action = "update" if any(item["name"].casefold() == name.casefold() for item in apps) else "add"
mutate_app_registry({"action": action, "name": name, "app": app})
PY

echo "OmniRoute is running on loopback ports 20128, 20129, and 20132."
echo "The owner login password is stored in $CONFIG_DIR/omniroute.env."
