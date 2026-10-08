#!/bin/sh
set -eu

ROOT=/opt/huou07-playground
SERVICE=huou07-playground.service

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root (for example: sudo ./deploy/uninstall.sh)." >&2
  exit 1
fi
if [ -e "/etc/systemd/system/$SERVICE" ] && ! grep -Fq 'ExecStart=/usr/bin/python3 /opt/huou07-playground/current/web/app.py' "/etc/systemd/system/$SERVICE"; then
  echo "An unrelated $SERVICE unit exists; refusing to remove it." >&2
  exit 1
fi
if systemctl is-active --quiet "$SERVICE"; then
  systemctl stop "$SERVICE"
fi
systemctl disable "$SERVICE" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
rm -rf "$ROOT"
echo "Removed huou07 playground code and service. The dedicated system account was retained."
