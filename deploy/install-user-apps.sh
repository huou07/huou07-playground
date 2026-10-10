#!/bin/sh
set -eu

ACTION=${1:-check}
USER_NAME=huou07
HOME_DIR=/home/huou07
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
USER_UNITS="$HOME_DIR/.config/systemd/user"
QUADLETS="$HOME_DIR/.config/containers/systemd"
APP_CONFIG="$HOME_DIR/.config/huou07-playground"
LITELLM_CONFIG="$HOME_DIR/.config/litellm"
OMNIROUTE_CONFIG="$HOME_DIR/.config/omniroute"
APP_DATA="$HOME_DIR/.local/share/huou07-playground"
PORTS="3080 4096 4000 20128 20129 20132"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

check_identity() {
  [ "$(id -un)" = "$USER_NAME" ] || fail "Run as $USER_NAME, not $(id -un)."
  [ "$HOME" = "$HOME_DIR" ] || fail "HOME must be $HOME_DIR (got $HOME)."
  [ "$(id -u)" -ne 0 ] || fail 'Do not run this installer as root.'
  command -v systemctl >/dev/null || fail 'systemd user manager is unavailable.'
  command -v podman >/dev/null || fail 'Podman is required for the LiteLLM and OmniRoute Quadlets.'
  command -v npm >/dev/null || fail 'npm is required to install DSH and ACP.'
  command -v curl >/dev/null || fail 'curl is required for local health checks.'
  available_kib=$(df -Pk "$HOME_DIR" | awk 'NR == 2 {print $4}')
  [ -n "$available_kib" ] && [ "$available_kib" -ge 8388608 ] || fail 'At least 8 GiB of free space is required for the fresh images and app data.'
  [ -x "$HOME_DIR/.opencode/bin/opencode" ] || fail 'The existing OpenCode CLI wrapper is missing; install it through the official OpenCode installer first.'
  [ -x "$HOME_DIR/.local/bin/codex" ] || fail 'Codex CLI is missing; install it through the official Codex instructions first.'
  command -v /usr/lib/systemd/system-generators/podman-system-generator >/dev/null 2>&1 || fail 'Podman Quadlet generator is unavailable.'
  [ "$(podman info --format '{{.Host.CgroupsVersion}}' 2>/dev/null)" = 2 ] || fail 'Rootless Podman must be ready on cgroup v2.'
}

ports_free() {
  python3 - "$PORTS" <<'PY'
import socket, sys
busy = []
for port in map(int, sys.argv[1].split()):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            busy.append(port)
if busy:
    print("Ports already in use: " + ", ".join(map(str, busy)), file=sys.stderr)
    print("Stop the old playground-managed application services with the reviewed admin retire command, then retry.", file=sys.stderr)
    raise SystemExit(1)
PY
}

preflight() {
  check_identity
  ports_free
  [ ! -e "$HOME_DIR/.local/lib/node_modules/@deepseek-ai/dsh" ] || fail 'A DSH package already exists in ~/.local; inspect it before reinstalling.'
  [ ! -e "$HOME_DIR/.local/lib/node_modules/@agentclientprotocol/codex-acp" ] || fail 'Codex ACP already exists in ~/.local; inspect it before reinstalling.'
  [ ! -e "$HOME_DIR/.local/lib/node_modules/omniroute" ] || fail 'An OmniRoute package already exists in ~/.local; inspect it before reinstalling.'
  [ ! -e "$HOME_DIR/.dsh/profiles/web" ] || fail 'A DSH Web profile exists; move or remove that old experimental profile after confirming it is disposable.'
  [ ! -e "$HOME_DIR/.local/share/omniroute" ] || fail 'OmniRoute data already exists; move or remove that old experimental data after confirming it is disposable.'
  [ ! -e "$APP_CONFIG/opencode-web.env" ] || fail 'The playground OpenCode Web password file already exists; keep it or remove it yourself before a clean install.'
  for file in "$LITELLM_CONFIG/postgres.env" "$LITELLM_CONFIG/litellm.env" "$LITELLM_CONFIG/config.yaml" "$OMNIROUTE_CONFIG/omniroute.env"; do
    [ ! -e "$file" ] || fail "Application configuration already exists: $file"
  done
  for file in dsh.service opencode-web.service; do
    [ ! -e "$USER_UNITS/$file" ] || fail "User service already exists: $USER_UNITS/$file"
  done
  for file in litellm.pod litellm-postgres.volume litellm-db.container litellm.container \
    omniroute.pod omniroute-redis.volume omniroute-redis.container omniroute.container; do
    [ ! -e "$QUADLETS/$file" ] || fail "Quadlet already exists: $QUADLETS/$file"
  done
  printf 'Preflight passed for %s.\n' "$USER_NAME"
  printf 'Native Codex CLI: '; "$HOME_DIR/.local/bin/codex" --version
  if "$HOME_DIR/.local/bin/codex" login status 2>/dev/null | grep -qi 'logged in'; then
    printf 'Codex ChatGPT login: detected (credentials were not displayed).\n'
  else
    printf 'Codex login: owner sign-in may be required.\n'
  fi
  if "$HOME_DIR/.opencode/bin/opencode" auth list >/dev/null 2>&1; then
    printf 'OpenCode auth configuration: readable by its native CLI (values were not displayed).\n'
  else
    printf 'OpenCode provider sign-in may be required.\n'
  fi
  printf 'Rootless Podman and all playground application ports are ready.\n'
}

write_secret_file() {
  target=$1
  shift
  umask 077
  tmp="$target.tmp.$$"
  ( set -C; printf '%s\n' "$@" > "$tmp" )
  chmod 0600 "$tmp"
  mv "$tmp" "$target"
}

install_apps() {
  preflight
  command -v node >/dev/null || fail 'Node.js is required.'
  case "$(node -p 'process.versions.node.split(".")[0]')" in
    22|24|25|26) ;;
    *) fail 'Use the verified Node.js 24 runtime (the target currently has 24.21.0).';;
  esac
  mkdir -p "$HOME_DIR/.local/share/huou07-playground" "$APP_CONFIG" "$LITELLM_CONFIG" "$OMNIROUTE_CONFIG" \
    "$USER_UNITS" "$QUADLETS" "$HOME_DIR/.local/share/omniroute" "$HOME_DIR/Projects"
  chmod 0700 "$APP_CONFIG" "$APP_DATA" "$LITELLM_CONFIG" "$OMNIROUTE_CONFIG" "$HOME_DIR/.local/share/omniroute"

  npm install --global --prefix "$HOME_DIR/.local" --no-audit --no-fund \
    @deepseek-ai/dsh@0.2.0-rc.2 \
    @agentclientprotocol/codex-acp@2.2.2 \
    pnpm@11.7.0
  "$HOME_DIR/.local/bin/codex-acp" --version
  "$HOME_DIR/.local/bin/dsh" plugin --profile web add @zaimokuza/dsh-acp-adapter@0.2.0-rc.2.9

  install -m 0644 "$ROOT/deploy/dsh-dashboard-launcher.py" "$APP_DATA/dsh-dashboard-launcher.py"
  install -m 0644 "$ROOT/deploy/user/dsh.service" "$USER_UNITS/dsh.service"
  install -m 0644 "$ROOT/deploy/user/opencode-web.service" "$USER_UNITS/opencode-web.service"
  for file in litellm.pod litellm-postgres.volume litellm-db.container litellm.container \
    omniroute.pod omniroute-redis.volume omniroute-redis.container omniroute.container; do
    install -m 0644 "$ROOT/deploy/user/$file" "$QUADLETS/$file"
  done

  if [ ! -f "$APP_CONFIG/opencode-web.env" ]; then
    pass=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    write_secret_file "$APP_CONFIG/opencode-web.env" "OPENCODE_SERVER_USERNAME=opencode" "OPENCODE_SERVER_PASSWORD=$pass"
    unset pass
  fi
  if [ ! -f "$LITELLM_CONFIG/postgres.env" ]; then
    pgpass=$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')
    write_secret_file "$LITELLM_CONFIG/postgres.env" \
      "POSTGRES_DB=litellm" "POSTGRES_USER=litellm" "POSTGRES_PASSWORD=$pgpass"
    unset pgpass
  fi
  if [ ! -f "$LITELLM_CONFIG/litellm.env" ]; then
    master=$(python3 -c 'import secrets; print("sk-" + secrets.token_hex(32))')
    salt=$(python3 -c 'import secrets; print("sk-" + secrets.token_hex(32))')
    dbpass=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$LITELLM_CONFIG/postgres.env")
    write_secret_file "$LITELLM_CONFIG/litellm.env" \
      "LITELLM_MASTER_KEY=$master" "LITELLM_SALT_KEY=$salt" \
      "DATABASE_URL=postgresql://litellm:$dbpass@127.0.0.1:5432/litellm" "STORE_MODEL_IN_DB=True"
    unset master salt dbpass
  fi
  if [ ! -f "$OMNIROUTE_CONFIG/omniroute.env" ]; then
    password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    write_secret_file "$OMNIROUTE_CONFIG/omniroute.env" \
      'APP_BIND_HOST=127.0.0.1' 'DASHBOARD_PORT=20128' 'API_PORT=20129' 'LIVE_WS_PORT=20132' \
      'DATA_DIR=/app/data' 'REDIS_URL=redis://127.0.0.1:6379' 'REQUIRE_API_KEY=true' \
      "INITIAL_PASSWORD=$password" 'OMNIROUTE_MEMORY_MB=2048'
    unset password
  fi
  cat > "$LITELLM_CONFIG/config.yaml.tmp" <<'EOF'
model_list: []
EOF
  chmod 0600 "$LITELLM_CONFIG/config.yaml.tmp"
  mv -f "$LITELLM_CONFIG/config.yaml.tmp" "$LITELLM_CONFIG/config.yaml"

  systemctl --user daemon-reload
  systemctl --user enable --now dsh.service opencode-web.service
  systemctl --user enable litellm-pod.service litellm-postgres-volume.service litellm-db.service litellm.service \
    omniroute-pod.service omniroute-redis-volume.service omniroute-redis.service omniroute.service
  systemctl --user start litellm-pod.service litellm-postgres-volume.service litellm-db.service litellm.service
  systemctl --user start omniroute-pod.service omniroute-redis-volume.service omniroute-redis.service omniroute.service
  "$0" status
}

status() {
  check_identity
  for unit in dsh.service opencode-web.service litellm-pod.service litellm-db.service litellm.service omniroute-pod.service omniroute-redis.service omniroute.service; do
    printf '%-28s ' "$unit"
    systemctl --user is-active "$unit" || true
  done
  python3 - <<'PY'
import socket, urllib.error, urllib.request
from base64 import b64encode
from pathlib import Path
checks = {
    3080: None,
    4096: "http://127.0.0.1:4096/global/health",
    4000: "http://127.0.0.1:4000/health/readiness",
    20128: "http://127.0.0.1:20128/healthz",
}
for port, url in checks.items():
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2): pass
        if url:
            try:
                request = urllib.request.Request(url)
                if port == 4096:
                    values = dict(line.rstrip("\n").split("=", 1) for line in Path.home().joinpath(".config/huou07-playground/opencode-web.env").read_text().splitlines() if "=" in line)
                    credentials = f'{values["OPENCODE_SERVER_USERNAME"]}:{values["OPENCODE_SERVER_PASSWORD"]}'.encode()
                    request.add_header("Authorization", "Basic " + b64encode(credentials).decode())
                urllib.request.urlopen(request, timeout=3).close()
                result = "HTTP ready"
            except urllib.error.HTTPError as exc:
                result = "HTTP auth required" if exc.code == 401 else f"HTTP {exc.code}"
        else:
            result = "loopback listener ready"
    except OSError as exc:
        result = f"unavailable ({exc.__class__.__name__})"
    print(f"127.0.0.1:{port}: {result}")
PY
  printf 'Application secrets are stored with mode 0600 in ~/.config/huou07-playground, ~/.config/litellm and ~/.config/omniroute (values not displayed).\n'
}

resume_apps() {
  check_identity
  ports_free
  hold="$HOME_DIR/.local/share/huou07-playground/rollback/containers-systemd"
  [ -d "$hold" ] || fail "No preserved Quadlet rollback files exist at $hold."
  for file in litellm.pod litellm-postgres.volume litellm-db.container litellm.container \
    omniroute.pod omniroute-redis.volume omniroute-redis.container omniroute.container; do
    [ ! -e "$QUADLETS/$file" ] || fail "A current Quadlet exists; refusing to overwrite it: $QUADLETS/$file"
    [ -f "$hold/$file" ] || fail "A preserved Quadlet is missing: $hold/$file"
  done
  for file in "$APP_CONFIG/opencode-web.env" "$LITELLM_CONFIG/postgres.env" "$LITELLM_CONFIG/litellm.env" \
    "$LITELLM_CONFIG/config.yaml" "$OMNIROUTE_CONFIG/omniroute.env" "$APP_DATA/dsh-dashboard-launcher.py"; do
    [ -f "$file" ] || fail "Application state needed to resume is missing: $file"
  done
  [ -x "$HOME_DIR/.local/bin/dsh" ] && [ -x "$HOME_DIR/.local/bin/codex-acp" ] || fail 'The pinned DSH or Codex ACP executable is missing.'
  mkdir -p "$QUADLETS"
  mv "$hold"/*.pod "$hold"/*.volume "$hold"/*.container "$QUADLETS/"
  systemctl --user daemon-reload
  systemctl --user enable --now dsh.service opencode-web.service
  systemctl --user enable litellm-pod.service litellm-postgres-volume.service litellm-db.service litellm.service \
    omniroute-pod.service omniroute-redis-volume.service omniroute-redis.service omniroute.service
  systemctl --user start litellm-pod.service litellm-postgres-volume.service litellm-db.service litellm.service
  systemctl --user start omniroute-pod.service omniroute-redis-volume.service omniroute-redis.service omniroute.service
  rmdir "$hold"
  rmdir "$(dirname -- "$hold")" 2>/dev/null || true
  "$0" status
}

case "$ACTION" in
  check) preflight ;;
  install) install_apps ;;
  status) status ;;
  resume) resume_apps ;;
  *) fail 'Usage: deploy/install-user-apps.sh [check|install|resume|status]' ;;
esac
