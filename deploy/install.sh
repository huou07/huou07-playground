#!/bin/sh
set -eu

ROOT=/opt/huou07-playground
SERVICE=huou07-playground.service
ACCOUNT=huou07-playground
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install.sh)." >&2
  exit 1
fi
if [ ! -f "$SOURCE/web/app.py" ] || [ ! -f "$SOURCE/deploy/systemd/$SERVICE" ]; then
  echo "Run the installer from a complete huou07-playground checkout." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/web/app.py' "/etc/systemd/system/$SERVICE"; then
  echo "An unrelated $SERVICE unit already exists; refusing to replace it." >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1 || [ ! -d /run/systemd/system ]; then
  echo "A running systemd installation is required." >&2
  exit 1
fi

if getent passwd "$ACCOUNT" >/dev/null; then
  account=$(getent passwd "$ACCOUNT")
  account_uid=$(printf '%s\n' "$account" | cut -d: -f3)
  account_home=$(printf '%s\n' "$account" | cut -d: -f6)
  account_shell=$(printf '%s\n' "$account" | cut -d: -f7)
  if [ "$account_uid" -ge 1000 ] || [ "$account_home" != /nonexistent ] || [ "$account_shell" != /usr/sbin/nologin ] || ! getent group "$ACCOUNT" >/dev/null; then
    echo "The existing $ACCOUNT account does not match the dedicated service account; refusing to reuse it." >&2
    exit 1
  fi
else
  useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin "$ACCOUNT"
fi

install -d -o root -g root -m 0755 "$ROOT/releases"
install -d -o root -g "$ACCOUNT" -m 0750 /etc/huou07-playground
if [ ! -e /etc/huou07-playground/apps.json ]; then
  install -o root -g "$ACCOUNT" -m 0640 "$SOURCE/config/apps.example.json" /etc/huou07-playground/apps.json
fi
release="$ROOT/releases/$(date -u +%Y%m%d%H%M%S)-$$"
previous=$(readlink "$ROOT/current" 2>/dev/null || true)
rollback() {
  if [ -n "$previous" ]; then
    ln -sfn "$previous" "$ROOT/current.rollback"
    mv -Tf "$ROOT/current.rollback" "$ROOT/current"
    systemctl restart "$SERVICE" >/dev/null 2>&1 || true
  else
    systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
    rm -f "$ROOT/current"
  fi
}
on_error() {
  status=$?
  trap - EXIT HUP INT TERM
  rollback
  rm -rf "$release"
  exit "$status"
}
trap on_error EXIT HUP INT TERM

install -d -o root -g root -m 0755 "$release"
cp -R "$SOURCE/web" "$release/web"
chown -R root:root "$release"
find "$release" -type d -exec chmod 0755 {} +
find "$release" -type f -exec chmod 0644 {} +
ln -sfn "$release" "$ROOT/current.new"
mv -Tf "$ROOT/current.new" "$ROOT/current"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$SERVICE" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl enable "$SERVICE"
if systemctl is-active --quiet "$SERVICE"; then
  systemctl restart "$SERVICE"
else
  systemctl start "$SERVICE"
fi

if ! systemctl is-active --quiet "$SERVICE"; then
  echo "The service did not become active; the previous release has been restored." >&2
  exit 1
fi
trap - EXIT HUP INT TERM
echo "Installed and running at http://127.0.0.1:8765"
echo "Use an SSH tunnel to open it remotely: ssh -L 8765:127.0.0.1:8765 <your-ssh-alias>"
