#!/bin/sh
set -eu

SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SERVICE=huou07-dsh
APP_DIR=/opt/huou07-dsh
STATE_DIR=/var/lib/huou07-dsh
DSH_HOME_DIR=$STATE_DIR/dsh
WORKSPACE_DIR=/srv/huou07-dsh-workspaces
NODE_VERSION=22.23.3
NODE_SHA256=df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de
DSH_VERSION=0.2.0-rc.2
ADAPTER_VERSION=0.2.0-rc.2.9
CODEX_ACP_VERSION=2.1.1
PNPM_VERSION=11.7.0
DSH_PORT=$(/usr/bin/python3 "$SOURCE/web/private_services.py" --port dsh backend_port)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install-dsh.sh)." >&2
  exit 1
fi
if [ "$(dpkg --print-architecture)" != amd64 ]; then
  echo "This pinned Node.js runtime is for Debian x86_64." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1 || ! command -v sha256sum >/dev/null 2>&1; then
  echo "curl and sha256sum are required." >&2
  exit 1
fi

if ! getent passwd "$SERVICE" >/dev/null; then
  useradd --system --user-group --home-dir "$STATE_DIR" --create-home --shell /usr/sbin/nologin "$SERVICE"
fi
if ! getent group huou07-dsh-link >/dev/null; then
  groupadd --system huou07-dsh-link
fi
usermod -a -G huou07-dsh-link huou07-playground
install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/app" "$APP_DIR/downloads"
install -d -o root -g root -m 0755 /etc/huou07-playground
install -o root -g root -m 0644 "$SOURCE/deploy/private-services.json" /etc/huou07-playground/private-services.json
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$STATE_DIR" "$STATE_DIR/config" "$STATE_DIR/data" "$STATE_DIR/state" "$STATE_DIR/cache"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$DSH_HOME_DIR"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$STATE_DIR/.codex"
install -d -o "$SERVICE" -g "$SERVICE" -m 0700 "$WORKSPACE_DIR"

if [ ! -x "$APP_DIR/node/bin/node" ]; then
  archive="$APP_DIR/downloads/node-v${NODE_VERSION}-linux-x64.tar.xz"
  curl --fail --location --silent --show-error "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o "$archive"
  printf '%s  %s\n' "$NODE_SHA256" "$archive" | sha256sum --check --status || {
    rm -f "$archive"
    echo "The official Node.js archive did not match its published SHA-256." >&2
    exit 1
  }
  tar -xJf "$archive" -C "$APP_DIR" --strip-components=1 "node-v${NODE_VERSION}-linux-x64/bin" "node-v${NODE_VERSION}-linux-x64/lib"
  rm -f "$archive"
fi

if [ ! -x "$APP_DIR/node/bin/node" ]; then
  install -d -o root -g root -m 0755 "$APP_DIR/node"
  mv "$APP_DIR/bin" "$APP_DIR/node/bin"
  mv "$APP_DIR/lib" "$APP_DIR/node/lib"
fi

PATH="$APP_DIR/node/bin:$PATH"
export PATH

if [ ! -x "$APP_DIR/node/bin/pnpm" ]; then
  "$APP_DIR/node/bin/npm" install --global --prefix "$APP_DIR/node" --no-audit --no-fund "pnpm@$PNPM_VERSION"
fi

if [ ! -x "$APP_DIR/app/node_modules/.bin/dsh" ] || [ ! -x "$APP_DIR/app/node_modules/.bin/codex-acp" ]; then
  "$APP_DIR/node/bin/npm" install --prefix "$APP_DIR/app" --no-audit --no-fund --save-exact \
    "@deepseek-ai/dsh@$DSH_VERSION" \
    "@deepseek-ai/dsh-app-boot@$DSH_VERSION" \
    "@agentclientprotocol/codex-acp@$CODEX_ACP_VERSION" \
    "@zaimokuza/dsh-acp-adapter@$ADAPTER_VERSION"
fi

if ! grep -Rqs "$ADAPTER_VERSION" "$DSH_HOME_DIR/profiles/web" 2>/dev/null; then
  runuser -u "$SERVICE" -- env HOME="$STATE_DIR" DSH_HOME="$DSH_HOME_DIR" XDG_CONFIG_HOME="$STATE_DIR/config" XDG_DATA_HOME="$STATE_DIR/data" XDG_STATE_HOME="$STATE_DIR/state" XDG_CACHE_HOME="$STATE_DIR/cache" PATH="$APP_DIR/node/bin:/usr/bin:/bin" "$APP_DIR/app/node_modules/.bin/dsh" plugin --profile web add "@zaimokuza/dsh-acp-adapter@$ADAPTER_VERSION"
fi

python3 "$SOURCE/deploy/patch_dsh_workspace_policy.py" apply
python3 "$SOURCE/deploy/patch_dsh_directory_picker.py" apply

install -d -o root -g root -m 0755 /usr/local/libexec/huou07-dsh
install -o root -g root -m 0755 "$SOURCE/deploy/dsh-launcher.py" /usr/local/libexec/huou07-dsh/launcher.py
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/huou07-dsh.service" /etc/systemd/system/huou07-dsh.service
install -o root -g root -m 0644 "$SOURCE/deploy/systemd/huou07-playground.service" /etc/systemd/system/huou07-playground.service
systemctl daemon-reload
systemctl enable --now huou07-dsh.service
systemctl restart huou07-dsh.service
systemctl restart huou07-playground.service

APPS_FILE=/var/lib/huou07-playground/apps.json python3 "$SOURCE/deploy/register_app.py" \
  --name "DeepSeek Harness" \
  --url "http://127.0.0.1:$DSH_PORT/" \
  --category "Coding Agents" \
  --description "Private agent workspace with native ACP integrations." \
  --health-url "http://127.0.0.1:$DSH_PORT/favicon.svg" \
  --health-method GET \
  --migrate-health-from "http://127.0.0.1:$DSH_PORT/"

echo "DSH $DSH_VERSION is installed as $SERVICE with the pinned ACP adapter and Codex ACP runtime."
echo "Service is loopback-only on port $DSH_PORT; allowed writes are limited to its private state and workspace."
echo "Owner sign-in and provider configuration remain manual."
