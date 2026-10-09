#!/bin/sh
set -eu

ROOT=/opt/huou07-playground
SERVICE=huou07-playground.service
POWER_SERVICE=huou07-playground-power.service
POWER_TIMER=huou07-playground-power.timer
GPU_SERVICE=huou07-playground-gpu.service
GPU_TIMER=huou07-playground-gpu.timer
ACCOUNT=huou07-playground
CONFIG_DIR=/etc/huou07-playground
STATE_DIR=/var/lib/huou07-playground
LEGACY_APPS_FILE=$CONFIG_DIR/apps.json
APPS_FILE=$STATE_DIR/apps.json
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install.sh)." >&2
  exit 1
fi
if [ ! -f "$SOURCE/web/app.py" ] || [ ! -f "$SOURCE/deploy/systemd/$SERVICE" ] || [ ! -f "$SOURCE/deploy/power.py" ] || [ ! -f "$SOURCE/deploy/systemd/$POWER_SERVICE" ] || [ ! -f "$SOURCE/deploy/systemd/$POWER_TIMER" ] || [ ! -f "$SOURCE/deploy/gpu.py" ] || [ ! -f "$SOURCE/deploy/systemd/$GPU_SERVICE" ] || [ ! -f "$SOURCE/deploy/systemd/$GPU_TIMER" ] || [ ! -f "$SOURCE/deploy/state.py" ]; then
  echo "Run the installer from a complete huou07-playground checkout." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/web/app.py' "/etc/systemd/system/$SERVICE"; then
  echo "An unrelated $SERVICE unit already exists; refusing to replace it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$POWER_SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/deploy/power.py' "/etc/systemd/system/$POWER_SERVICE"; then
  echo "An unrelated $POWER_SERVICE unit already exists; refusing to replace it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$POWER_TIMER" ] && ! grep -Fq "Unit=$POWER_SERVICE" "/etc/systemd/system/$POWER_TIMER"; then
  echo "An unrelated $POWER_TIMER unit already exists; refusing to replace it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$GPU_SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/deploy/gpu.py' "/etc/systemd/system/$GPU_SERVICE"; then
  echo "An unrelated $GPU_SERVICE unit already exists; refusing to replace it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$GPU_TIMER" ] && ! grep -Fq "Unit=$GPU_SERVICE" "/etc/systemd/system/$GPU_TIMER"; then
  echo "An unrelated $GPU_TIMER unit already exists; refusing to replace it." >&2
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
if [ -L "$CONFIG_DIR" ] || [ -L "$STATE_DIR" ] || [ -L "$LEGACY_APPS_FILE" ] || [ -L "$APPS_FILE" ]; then
  echo "The application registry must not be a symbolic link." >&2
  exit 1
fi
if { [ -e "$STATE_DIR" ] && [ ! -d "$STATE_DIR" ]; } || { [ -e "$LEGACY_APPS_FILE" ] && [ ! -f "$LEGACY_APPS_FILE" ]; }; then
  echo "The application registry path is not a regular file or directory." >&2
  exit 1
fi
if [ -e "$APPS_FILE" ] && [ ! -f "$APPS_FILE" ]; then
  echo "The application registry path is not a regular file." >&2
  exit 1
fi
install -d -o root -g root -m 0755 "$CONFIG_DIR"
install -d -o "$ACCOUNT" -g "$ACCOUNT" -m 0750 "$STATE_DIR"
chown "$ACCOUNT":"$ACCOUNT" "$STATE_DIR"
chmod 0750 "$STATE_DIR"
if [ ! -e "$APPS_FILE" ]; then
  if [ -f "$LEGACY_APPS_FILE" ]; then
    install -o "$ACCOUNT" -g "$ACCOUNT" -m 0660 "$LEGACY_APPS_FILE" "$APPS_FILE"
  else
    install -o "$ACCOUNT" -g "$ACCOUNT" -m 0660 "$SOURCE/config/apps.example.json" "$APPS_FILE"
  fi
fi
chown "$ACCOUNT":"$ACCOUNT" "$APPS_FILE"
chmod 0660 "$APPS_FILE"
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
install -d -o root -g root -m 0755 "$release/deploy"
install -o root -g root -m 0644 "$SOURCE/deploy/state.py" "$release/deploy/state.py"
install -o root -g root -m 0644 "$SOURCE/deploy/power.py" "$release/deploy/power.py"
install -o root -g root -m 0644 "$SOURCE/deploy/gpu.py" "$release/deploy/gpu.py"
if [ ! -f "$release/web/static/branding.png" ]; then
  for branding in "$ROOT"/releases/*/web/static/branding.png; do
    if [ -f "$branding" ]; then
      cp "$branding" "$release/web/static/branding.png"
      break
    fi
  done
fi
chown -R root:root "$release"
find "$release" -type d -exec chmod 0755 {} +
find "$release" -type f -exec chmod 0644 {} +
ln -sfn "$release" "$ROOT/current.new"
mv -Tf "$ROOT/current.new" "$ROOT/current"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$SERVICE" "/etc/systemd/system/$SERVICE"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$POWER_SERVICE" "/etc/systemd/system/$POWER_SERVICE"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$POWER_TIMER" "/etc/systemd/system/$POWER_TIMER"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$GPU_SERVICE" "/etc/systemd/system/$GPU_SERVICE"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$GPU_TIMER" "/etc/systemd/system/$GPU_TIMER"
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
if ! systemctl enable --now "$POWER_TIMER" >/dev/null 2>&1; then
  echo "Warning: CPU package power sampling could not be scheduled; the dashboard will report it unavailable." >&2
fi
has_i915=0
for gpu_card in /sys/class/drm/card[0-9]*; do
  [ -e "$gpu_card/device/driver" ] || continue
  card_number=${gpu_card##*/card}
  case "$card_number" in ''|*[!0-9]*) continue ;; esac
  if [ "$(basename "$(readlink -f "$gpu_card/device/driver")")" = i915 ]; then
    has_i915=1
    break
  fi
done
if command -v intel_gpu_top >/dev/null 2>&1 && [ "$has_i915" -eq 1 ]; then
  if systemctl start "$GPU_SERVICE" >/dev/null 2>&1 && systemctl enable --now "$GPU_TIMER" >/dev/null 2>&1; then
    echo "Intel GPU sampling enabled with the restricted i915 collector."
  else
    echo "Warning: Intel GPU sampling could not start; the dashboard will report it unavailable." >&2
  fi
else
  systemctl disable --now "$GPU_TIMER" >/dev/null 2>&1 || true
fi
if [ -x "$SOURCE/deploy/configure-wg-private-web-access.sh" ]; then
  "$SOURCE/deploy/configure-wg-private-web-access.sh" || echo "Warning: private WireGuard application firewall rules were not configured." >&2
fi
trap - EXIT HUP INT TERM
echo "Installed and running at http://127.0.0.1:8765"
echo "Use an SSH tunnel to open it remotely: ssh -L 8765:127.0.0.1:8765 <your-ssh-alias>"
