#!/bin/sh
set -eu

ROOT=/opt/huou07-playground
SERVICE=huou07-playground.service
POWER_SERVICE=huou07-playground-power.service
POWER_TIMER=huou07-playground-power.timer
GPU_SERVICE=huou07-playground-gpu.service
GPU_TIMER=huou07-playground-gpu.timer

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root (for example: sudo ./deploy/uninstall.sh)." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/web/app.py' "/etc/systemd/system/$SERVICE"; then
  echo "An unrelated $SERVICE unit exists; refusing to remove it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$POWER_SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/deploy/power.py' "/etc/systemd/system/$POWER_SERVICE"; then
  echo "An unrelated $POWER_SERVICE unit exists; refusing to remove it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$POWER_TIMER" ] && ! grep -Fq "Unit=$POWER_SERVICE" "/etc/systemd/system/$POWER_TIMER"; then
  echo "An unrelated $POWER_TIMER unit exists; refusing to remove it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$GPU_SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/deploy/gpu.py' "/etc/systemd/system/$GPU_SERVICE"; then
  echo "An unrelated $GPU_SERVICE unit exists; refusing to remove it." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$GPU_TIMER" ] && ! grep -Fq "Unit=$GPU_SERVICE" "/etc/systemd/system/$GPU_TIMER"; then
  echo "An unrelated $GPU_TIMER unit exists; refusing to remove it." >&2
  exit 1
fi
if systemctl is-active --quiet "$SERVICE"; then
  systemctl stop "$SERVICE"
fi
systemctl disable "$SERVICE" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/$SERVICE"
systemctl disable --now "$POWER_TIMER" >/dev/null 2>&1 || true
systemctl stop "$POWER_SERVICE" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/$POWER_SERVICE" "/etc/systemd/system/$POWER_TIMER"
systemctl disable --now "$GPU_TIMER" >/dev/null 2>&1 || true
systemctl stop "$GPU_SERVICE" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/$GPU_SERVICE" "/etc/systemd/system/$GPU_TIMER"
systemctl daemon-reload
rm -rf /var/lib/huou07-playground-gpu
rm -rf "$ROOT"
echo "Removed huou07 playground code and service. The dedicated system account was retained."
