#!/bin/sh
set -eu

SERVICE=huou07-litellm
STATE_DIR=/var/lib/$SERVICE
CONFIG_DIR=/etc/$SERVICE
LIBEXEC_DIR=/usr/local/libexec/$SERVICE
NETWORK=$SERVICE
DATABASE_VOLUME=$SERVICE-postgres
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install-litellm.sh)." >&2
  exit 1
fi
if [ ! -x /usr/bin/podman ] || [ ! -x /usr/bin/slirp4netns ] || [ ! -x /usr/bin/systemctl ] || [ ! -d /run/systemd/system ]; then
  echo "A running systemd installation with Podman and slirp4netns is required." >&2
  exit 1
fi
if [ ! -f /var/lib/huou07-playground/apps.json ] || [ ! -d /opt/huou07-playground/current ]; then
  echo "Install huou07 playground before the LiteLLM integration." >&2
  exit 1
fi
proxy_unit="/etc/systemd/system/$SERVICE.service"
if [ -e "$proxy_unit" ] && {
  ! grep -Fqx "Description=huou07 LiteLLM gateway" "$proxy_unit" ||
  ! grep -Fq -- "--name $SERVICE-proxy" "$proxy_unit" ||
  ! grep -Fq "ghcr.io/berriai/litellm:v1.103.1" "$proxy_unit"
}; then
  echo "An unrelated $SERVICE.service unit already exists; refusing to replace it." >&2
  exit 1
fi
database_unit="/etc/systemd/system/$SERVICE-db.service"
if [ -e "$database_unit" ] && {
  ! grep -Fqx "Description=huou07 LiteLLM PostgreSQL database" "$database_unit" ||
  ! grep -Fq -- "--name $SERVICE-db" "$database_unit" ||
  ! grep -Fq "docker.io/library/postgres:16" "$database_unit"
}; then
  echo "An unrelated $SERVICE-db.service unit already exists; refusing to replace it." >&2
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

install -d -o "$SERVICE" -g "$SERVICE" -m 0750 "$STATE_DIR"
install -d -o root -g root -m 0755 "$CONFIG_DIR" "$LIBEXEC_DIR"
if [ -L "$CONFIG_DIR/config.yaml" ]; then
  echo "The LiteLLM base config must not be a symbolic link." >&2
  exit 1
fi
install -o root -g root -m 0644 "$SOURCE/deploy/litellm-config.yaml" "$CONFIG_DIR/config.yaml"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$STATE_DIR/.config/containers"
containers_config="$STATE_DIR/.config/containers/containers.conf"
if [ -e "$containers_config" ]; then
  if [ -L "$containers_config" ] || ! grep -Eq '^[[:space:]]*default_rootless_network_cmd[[:space:]]*=[[:space:]]*"slirp4netns"$' "$containers_config"; then
    echo "The dedicated LiteLLM account has an incompatible Podman configuration; refusing to replace it." >&2
    exit 1
  fi
  if grep -Eq '^[[:space:]]*cgroup_manager[[:space:]]*=' "$containers_config"; then
    if ! grep -Eq '^[[:space:]]*cgroup_manager[[:space:]]*=[[:space:]]*"cgroupfs"$' "$containers_config"; then
      echo "The dedicated LiteLLM account has an incompatible Podman cgroup manager; refusing to replace it." >&2
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
install -o root -g root -m 0755 "$SOURCE/deploy/litellm-prepare.sh" "$LIBEXEC_DIR/prepare.sh"
install -o root -g root -m 0755 "$SOURCE/deploy/litellm-wait-postgres.sh" "$LIBEXEC_DIR/wait-postgres.sh"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/huou07-litellm-db.service" "/etc/systemd/system/$SERVICE-db.service"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/huou07-litellm.service" "/etc/systemd/system/$SERVICE.service"

if [ -e "$CONFIG_DIR/postgres.env" ] && [ -L "$CONFIG_DIR/postgres.env" ]; then
  echo "The LiteLLM PostgreSQL environment must not be a symbolic link." >&2
  exit 1
fi
if [ ! -e "$CONFIG_DIR/postgres.env" ]; then
  postgres_password=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  postgres_tmp=$(mktemp "$CONFIG_DIR/.postgres.env.XXXXXX")
  printf 'POSTGRES_USER=litellm\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=litellm\n' "$postgres_password" > "$postgres_tmp"
  unset postgres_password
  chown root:root "$postgres_tmp"
  chmod 0600 "$postgres_tmp"
  mv "$postgres_tmp" "$CONFIG_DIR/postgres.env"
fi
chown root:root "$CONFIG_DIR/postgres.env"
chmod 0600 "$CONFIG_DIR/postgres.env"

if [ -e "$CONFIG_DIR/litellm.env" ] && [ -L "$CONFIG_DIR/litellm.env" ]; then
  echo "The LiteLLM environment must not be a symbolic link." >&2
  exit 1
fi
if [ ! -e "$CONFIG_DIR/litellm.env" ]; then
  postgres_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$CONFIG_DIR/postgres.env")
  master_key=$(python3 -c 'import secrets; print("sk-" + secrets.token_hex(32))')
  salt_key=$(python3 -c 'import secrets; print("sk-" + secrets.token_hex(32))')
  litellm_tmp=$(mktemp "$CONFIG_DIR/.litellm.env.XXXXXX")
  printf 'LITELLM_MASTER_KEY=%s\nLITELLM_SALT_KEY=%s\nDATABASE_URL=postgresql://litellm:%s@127.0.0.1:5432/litellm\n' "$master_key" "$salt_key" "$postgres_password" > "$litellm_tmp"
  unset postgres_password master_key salt_key
  chown root:root "$litellm_tmp"
  chmod 0600 "$litellm_tmp"
  mv "$litellm_tmp" "$CONFIG_DIR/litellm.env"
fi
chown root:root "$CONFIG_DIR/litellm.env"
chmod 0600 "$CONFIG_DIR/litellm.env"

python3 - "$CONFIG_DIR/litellm.env" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()
old = b"@huou07-litellm-db:5432/litellm"
new = b"@127.0.0.1:5432/litellm"
if data.count(old) == 1:
    data = data.replace(old, new)
elif data.count(new) != 1:
    raise SystemExit("LiteLLM database URL is not in a supported format.")
fd, temporary = tempfile.mkstemp(prefix=".litellm.env.", dir=path.parent)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
    os.replace(temporary, path)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY

python3 - "$CONFIG_DIR" <<'PY'
import re
import sys
from pathlib import Path

directory = Path(sys.argv[1])
def read_env(name, expected):
    text = (directory / name).read_text(encoding="ascii")
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in expected or key in values or not value or re.search(r"\s", value):
            raise SystemExit(f"Invalid private LiteLLM environment file: {name}")
        values[key] = value
    if set(values) != expected:
        raise SystemExit(f"Incomplete private LiteLLM environment file: {name}")
    return values

database = read_env("postgres.env", {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"})
gateway = read_env("litellm.env", {"LITELLM_MASTER_KEY", "LITELLM_SALT_KEY", "DATABASE_URL"})
key_ok = lambda value: value.startswith("sk-") and value[3:].isalnum()
if (database["POSTGRES_USER"], database["POSTGRES_DB"]) != ("litellm", "litellm"):
    raise SystemExit("Invalid private LiteLLM database identity.")
if not database["POSTGRES_PASSWORD"].isalnum() or not all(key_ok(gateway[key]) for key in ("LITELLM_MASTER_KEY", "LITELLM_SALT_KEY")):
    raise SystemExit("Invalid private LiteLLM key format.")
expected_url = f"postgresql://litellm:{database['POSTGRES_PASSWORD']}@127.0.0.1:5432/litellm"
if gateway["DATABASE_URL"] != expected_url:
    raise SystemExit("LiteLLM and PostgreSQL credentials do not match.")
PY

install -d -o "$SERVICE" -g "$SERVICE" -m 0700 /run/huou07-litellm
run_as_litellm() {
  runuser -u "$SERVICE" -- env HOME="$STATE_DIR" XDG_RUNTIME_DIR=/run/huou07-litellm "$@"
}
run_as_litellm /usr/bin/podman info >/dev/null
run_as_litellm /usr/local/libexec/huou07-litellm/prepare.sh
if ! run_as_litellm /usr/bin/podman image exists docker.io/library/postgres:16; then
  run_as_litellm /usr/bin/podman pull docker.io/library/postgres:16
fi
if ! run_as_litellm /usr/bin/podman image exists ghcr.io/berriai/litellm:v1.103.1; then
  run_as_litellm /usr/bin/podman pull ghcr.io/berriai/litellm:v1.103.1
fi

systemctl daemon-reload
systemctl enable "$SERVICE-db.service" "$SERVICE.service"
systemctl restart "$SERVICE-db.service"
systemctl restart "$SERVICE.service"
attempt=0
while [ "$attempt" -lt 120 ]; do
  db_state=$(systemctl show --property=ActiveState --value "$SERVICE-db.service")
  gateway_state=$(systemctl show --property=ActiveState --value "$SERVICE.service")
  if [ "$db_state" = active ] && [ "$gateway_state" = active ] && \
     python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:4000/health/liveliness", timeout=2).read()' >/dev/null 2>&1; then
    break
  fi
  if [ "$db_state" = failed ] || [ "$gateway_state" = failed ]; then
    echo "LiteLLM or PostgreSQL failed to start; inspect their systemd journals." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 1
done
if [ "$attempt" -ge 120 ]; then
  echo "LiteLLM or PostgreSQL did not become active." >&2
  exit 1
fi
APPS_FILE=/var/lib/huou07-playground/apps.json python3 "$SOURCE/deploy/register_app.py" \
  --name "LiteLLM Gateway" \
  --url http://127.0.0.1:4000/ui \
  --category "AI Gateway" \
  --description "OpenAI-compatible gateway. Sign in to add providers and models." \
  --health-url http://127.0.0.1:4000/health/liveliness \
  --management-url http://127.0.0.1:4000/ui

echo "LiteLLM is running on 127.0.0.1:4000 as $SERVICE."
echo "Add SSH local port 4000 forwarding before opening its Admin UI."
echo "Generated credentials are stored in $CONFIG_DIR/litellm.env; do not copy that file into the repository."
