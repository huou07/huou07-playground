#!/bin/sh
set -eu

SERVICE=huou07-wg-easy
STATE_DIR=/var/lib/$SERVICE
CONFIG_DIR=/etc/$SERVICE
LIBEXEC_DIR=/usr/local/libexec/$SERVICE
STATUS_SERVICE=huou07-playground-wg-status.service
STATUS_TIMER=huou07-playground-wg-status.timer
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IMAGE=ghcr.io/wg-easy/wg-easy@sha256:6b89677a396dc2831d3b5b74d720d6d50c38fd2cbe9071bc8419453f236a94b3

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install-wg-easy.sh)." >&2
  exit 1
fi
if [ ! -x /usr/bin/podman ] || [ ! -x /usr/bin/wg ] || [ ! -x /usr/sbin/modprobe ] || [ ! -x /usr/bin/systemctl ] || [ ! -d /run/systemd/system ]; then
  echo "A running systemd installation with rootful Podman and wireguard-tools is required." >&2
  exit 1
fi
if [ ! -c /dev/net/tun ] || [ ! -f "$SOURCE/deploy/systemd/$SERVICE.service" ] || [ ! -f "$SOURCE/deploy/wg_status.py" ] || [ ! -f "$SOURCE/deploy/systemd/$STATUS_SERVICE" ] || [ ! -f "$SOURCE/deploy/systemd/$STATUS_TIMER" ]; then
  echo "The host WireGuard device or service unit is missing." >&2
  exit 1
fi
unit="/etc/systemd/system/$SERVICE.service"
if [ -e "$unit" ] && {
  ! grep -Fqx "Description=huou07 WireGuard Easy administration" "$unit" ||
  ! grep -Fq "$IMAGE" "$unit"
}; then
  echo "An unrelated $SERVICE.service unit already exists; refusing to replace it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$STATUS_SERVICE" ] && ! grep -Fqx "Description=Collect secret-free WireGuard status for huou07 playground" "/etc/systemd/system/$STATUS_SERVICE"; then
  echo "An unrelated $STATUS_SERVICE unit already exists; refusing to replace it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$STATUS_TIMER" ] && ! grep -Fqx "Description=Refresh huou07 playground WireGuard status" "/etc/systemd/system/$STATUS_TIMER"; then
  echo "An unrelated $STATUS_TIMER unit already exists; refusing to replace it." >&2
  exit 1
fi

install -d -o root -g root -m 0700 "$STATE_DIR" "$CONFIG_DIR"
install -d -o root -g root -m 0755 "$LIBEXEC_DIR"
/usr/sbin/modprobe wireguard
install -o root -g root -m 0755 "$SOURCE/deploy/wg-easy-wait-ready.sh" "$LIBEXEC_DIR/wait-ready.sh"
install -o root -g root -m 0755 "$SOURCE/deploy/wg_status.py" "$LIBEXEC_DIR/status.py"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$SERVICE.service" "$unit"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$STATUS_SERVICE" "/etc/systemd/system/$STATUS_SERVICE"
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/$STATUS_TIMER" "/etc/systemd/system/$STATUS_TIMER"
if ! /usr/bin/podman image exists "$IMAGE"; then
  /usr/bin/podman pull "$IMAGE"
fi

systemctl daemon-reload
systemctl enable "$SERVICE.service"
systemctl enable --now "$STATUS_TIMER"
systemctl restart "$SERVICE.service"
systemctl start "$STATUS_SERVICE"
attempt=0
while [ "$attempt" -lt 80 ]; do
  state=$(systemctl show --property=ActiveState --value "$SERVICE.service")
  if [ "$state" = active ] && /usr/bin/curl --fail --silent --max-time 3 http://127.0.0.1:51821/ >/dev/null 2>&1; then
    break
  fi
  if [ "$state" = failed ]; then
    echo "wg-easy failed to start; inspect its systemd status without publishing logs." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 1
done
if [ "$attempt" -ge 80 ]; then
  echo "wg-easy did not become ready on loopback." >&2
  exit 1
fi

APPS_FILE=/var/lib/huou07-playground/apps.json python3 "$SOURCE/deploy/register_app.py" \
  --name "WireGuard Easy" \
  --url http://127.0.0.1:51821/ \
  --category "Network & VPN" \
  --description "Manage private WireGuard peers through WireGuard or the SSH recovery tunnel." \
  --health-url http://127.0.0.1:51821/ \
  --management-url http://127.0.0.1:51821/

echo "wg-easy is running on 127.0.0.1:51821."
echo "Open it through the private dashboard or forward the admin port over SSH to finish owner setup. The separate status collector exposes no keys or peer addresses."
