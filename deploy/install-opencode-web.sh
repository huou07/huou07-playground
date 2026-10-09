#!/bin/sh
set -eu

SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVICE=huou07-opencode
WORKSPACE_GROUP=huou07-opencode-workspaces
STATE_DIR=/var/lib/huou07-opencode
WORKSPACE_DIR=/srv/huou07-opencode-workspaces
BIN_DIR=/usr/local/libexec/huou07-opencode
CONFIG_DIR=/var/lib/huou07-opencode/config/opencode
CONFIG=/var/lib/huou07-opencode/config/opencode/opencode.json
CONFIG_DIGEST=/etc/huou07-playground/opencode-web.config.sha256
ENV_FILE=/etc/huou07-playground/opencode-web.env
UNIT=/etc/systemd/system/huou07-opencode-web.service
UNIT_DIGEST=/etc/huou07-playground/opencode-web.unit.sha256

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install-opencode-web.sh)." >&2
  exit 1
fi
OWNER=${SUDO_USER:-}
if [ -z "$OWNER" ] || [ "$OWNER" = root ]; then
  echo "Run this with sudo from the normal SSH owner's account." >&2
  exit 1
fi
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
SOURCE_BINARY="$OWNER_HOME/.opencode/bin/opencode.real"
if [ -z "$OWNER_HOME" ] || [ ! -f "$SOURCE_BINARY" ] || [ -L "$SOURCE_BINARY" ] || [ ! -x "$SOURCE_BINARY" ]; then
  echo "The isolated OpenCode CLI is missing for $OWNER; install it and run deploy/install-opencode-launcher.sh first." >&2
  exit 1
fi
if [ ! -d /etc/huou07-playground ]; then
  echo "Install huou07 playground before its OpenCode web integration." >&2
  exit 1
fi
if ! command -v bwrap >/dev/null 2>&1; then
  echo "Install bubblewrap before enabling the isolated OpenCode web shell." >&2
  exit 1
fi
if [ -e "$UNIT" ] && ! cmp -s "$SOURCE/deploy/systemd/huou07-opencode-web.service" "$UNIT"; then
  if [ -L "$UNIT_DIGEST" ] || [ ! -f "$UNIT_DIGEST" ] || [ "$(sha256sum "$UNIT" | cut -d' ' -f1)" != "$(cat "$UNIT_DIGEST")" ]; then
    echo "$UNIT has local changes; review them before upgrading." >&2
    exit 1
  fi
fi
if [ -e "$CONFIG" ] && ! cmp -s "$SOURCE/config/opencode.json" "$CONFIG"; then
  installed_digest=$(sha256sum "$CONFIG" | cut -d' ' -f1)
  if [ -f "$CONFIG_DIGEST" ]; then
    expected_digest=$(cat "$CONFIG_DIGEST")
  else
    expected_digest=df1ee2770ff9f3a4ed8b0f492969be2481f959aa8b959a33ddf6717a238cfdb1
  fi
  if [ "$installed_digest" != "$expected_digest" ]; then
    echo "$CONFIG has local changes; review and merge them manually." >&2
    exit 1
  fi
fi
if [ -e "$ENV_FILE" ] && [ -L "$ENV_FILE" ]; then
  echo "The OpenCode server environment must not be a symbolic link." >&2
  exit 1
fi

if ! getent group "$SERVICE" >/dev/null; then
  groupadd --system "$SERVICE"
fi
if ! getent group "$WORKSPACE_GROUP" >/dev/null; then
  groupadd --system "$WORKSPACE_GROUP"
fi
if ! getent passwd "$SERVICE" >/dev/null; then
  useradd --system --gid "$SERVICE" --home-dir "$STATE_DIR" --create-home --shell /usr/sbin/nologin "$SERVICE"
fi
usermod -a -G "$WORKSPACE_GROUP" "$OWNER"
usermod -a -G "$WORKSPACE_GROUP" "$SERVICE"

install -d -o root -g root -m 0755 "$BIN_DIR"
install -o root -g root -m 0755 "$SOURCE_BINARY" "$BIN_DIR/opencode"
install -o root -g root -m 0755 "$SOURCE/deploy/opencode-bash-sandbox" "$BIN_DIR/bash"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$STATE_DIR" "$STATE_DIR/data" "$STATE_DIR/state" "$STATE_DIR/cache"
install -d -o root -g "$SERVICE" -m 0750 "$STATE_DIR/config" "$CONFIG_DIR"
config_tmp=$(mktemp "${CONFIG}.XXXXXX")
install -o root -g "$SERVICE" -m 0640 "$SOURCE/config/opencode.json" "$config_tmp"
mv -f "$config_tmp" "$CONFIG"
config_digest_tmp=$(mktemp "${CONFIG_DIGEST}.XXXXXX")
sha256sum "$CONFIG" | cut -d' ' -f1 > "$config_digest_tmp"
chown root:root "$config_digest_tmp"
chmod 0644 "$config_digest_tmp"
mv -f "$config_digest_tmp" "$CONFIG_DIGEST"
install -d -o "$SERVICE" -g "$WORKSPACE_GROUP" -m 2770 "$WORKSPACE_DIR"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/huou07-opencode-web.service" "$UNIT"
digest=$(sha256sum "$UNIT" | cut -d' ' -f1)
digest_tmp=$(mktemp "${UNIT_DIGEST}.XXXXXX")
printf '%s\n' "$digest" > "$digest_tmp"
chown root:root "$digest_tmp"
chmod 0644 "$digest_tmp"
mv -f "$digest_tmp" "$UNIT_DIGEST"

if [ ! -e "$ENV_FILE" ]; then
  password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  (umask 077; printf 'OPENCODE_SERVER_PASSWORD=%s\n' "$password" > "$ENV_FILE")
  unset password
fi
chown root:root "$ENV_FILE"
chmod 0600 "$ENV_FILE"

systemctl daemon-reload
if systemctl is-active --quiet huou07-opencode-web.service; then
  systemctl restart huou07-opencode-web.service
else
  systemctl enable --now huou07-opencode-web.service
fi
echo "OpenCode web is running as $SERVICE on 127.0.0.1:4096."
echo "Only $WORKSPACE_DIR is shared with the SSH owner; the service cannot see user home directories."
echo "OpenCode shell commands run with bubblewrap and can write only to the selected project."
echo "The browser login password is in $ENV_FILE; read it with sudo when connecting over an SSH tunnel."
