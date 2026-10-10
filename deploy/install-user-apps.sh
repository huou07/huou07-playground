#!/bin/sh
set -eu

ACTION=${1:-prepare}
USER_NAME=huou07
HOME_DIR=/home/huou07
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
USER_UNITS="$HOME_DIR/.config/systemd/user"
QUADLETS="$HOME_DIR/.config/containers/systemd"
APP_CONFIG="$HOME_DIR/.config/huou07-playground"
LITELLM_CONFIG="$HOME_DIR/.config/litellm"
OMNIROUTE_CONFIG="$HOME_DIR/.config/omniroute"
APP_DATA="$HOME_DIR/.local/share/huou07-playground"
TOOLS_DIR="$APP_DATA/tools"
READY_FILE="$APP_DATA/readiness.json"
PORTS="3080 4096 4000 20128 20129 20132"
DSH_VERSION=0.2.0-rc.2
ACP_VERSION=2.2.2
ADAPTER_VERSION=0.2.0-rc.2.9
PNPM_VERSION=11.7.0
LITELLM_IMAGE=ghcr.io/berriai/litellm:v1.104.2
POSTGRES_IMAGE=docker.io/library/postgres:16
OMNIROUTE_IMAGE=docker.io/diegosouzapw/omniroute:3.8.51
REDIS_IMAGE=docker.io/library/redis:8.6.5-alpine

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

check_identity() {
  [ "$(id -un)" = "$USER_NAME" ] || fail "Run as $USER_NAME, not $(id -un)."
  [ "$HOME" = "$HOME_DIR" ] || fail "HOME must be $HOME_DIR (got $HOME)."
  [ "$(id -u)" -ne 0 ] || fail 'Do not run this installer as root.'
  command -v systemctl >/dev/null || fail 'systemd user manager is unavailable.'
  command -v podman >/dev/null || fail 'Podman is required for the LiteLLM and OmniRoute Quadlets.'
  command -v npm >/dev/null || fail 'npm is required to install DSH and ACP.'
  command -v curl >/dev/null || fail 'curl is required for local health checks.'
  command -v python3 >/dev/null || fail 'Python 3 is required for local protocol and health checks.'
  available_kib=$(df -Pk "$HOME_DIR" | awk 'NR == 2 {print $4}')
  [ -n "$available_kib" ] && [ "$available_kib" -ge 8388608 ] || fail 'At least 8 GiB of free space is required for the fresh images and app data.'
  [ -x "$HOME_DIR/.opencode/bin/opencode" ] || fail 'The existing OpenCode CLI wrapper is missing; install it through the official OpenCode installer first.'
  [ -x "$HOME_DIR/.local/bin/codex" ] || fail 'Codex CLI is missing; install it through the official Codex instructions first.'
  [ -x /usr/lib/systemd/system-generators/podman-system-generator ] || fail 'Podman Quadlet generator is unavailable.'
  node_major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null) || fail 'Node.js is unavailable.'
  [ "$node_major" = 24 ] || fail 'Use the verified Node.js 24 runtime; the DSH adapter declares support for Node 22.19+ or 24+.'
  cgroups=$(podman info --format '{{.Host.CgroupsVersion}}' 2>/dev/null) || fail 'Rootless Podman information is unavailable.'
  [ "$cgroups" = v2 ] || fail "Rootless Podman requires cgroup v2 (reported: $cgroups)."
  rootless=$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null) || fail 'Rootless Podman status is unavailable.'
  [ "$rootless" = true ] || fail 'Podman is not running rootless under huou07.'
  runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
  [ -d "$runtime_dir" ] || fail 'The huou07 systemd runtime directory is unavailable.'
  systemctl --user show-environment >/dev/null 2>&1 || fail 'The huou07 systemd user manager is unavailable.'
  linger=$(loginctl show-user "$USER_NAME" --property=Linger --value 2>/dev/null || true)
  [ "$linger" = yes ] || fail 'Enable lingering for huou07 so user services survive logout and reboot.'
}

check_clean_inputs() {
  # The existing owner OpenCode and Codex installations are deliberately reused.
  # Refuse application-name collisions in huou07's rootless Podman store.
  for name in huou07-litellm huou07-litellm-db huou07-litellm-proxy huou07-omniroute huou07-omniroute-redis; do
    if podman container exists "$name" >/dev/null 2>&1; then
      fail "A rootless Podman container already uses the new app name '$name'; inspect it before continuing."
    else
      result=$?
      [ "$result" -eq 1 ] || fail 'Could not verify rootless Podman container names.'
    fi
  done
  for name in huou07-litellm-postgres huou07-omniroute-redis huou07-omniroute-data; do
    if podman volume exists "$name" >/dev/null 2>&1; then
      fail "A rootless Podman volume already uses the new app name '$name'; inspect it before continuing."
    else
      result=$?
      [ "$result" -eq 1 ] || fail 'Could not verify rootless Podman volume names.'
    fi
  done
  for name in huou07-litellm huou07-omniroute; do
    if podman pod exists "$name" >/dev/null 2>&1; then
      fail "A rootless Podman pod already uses the new app name '$name'; inspect it before continuing."
    else
      result=$?
      [ "$result" -eq 1 ] || fail 'Could not verify rootless Podman pod names.'
    fi
  done
  for path in "$HOME_DIR/.config" "$HOME_DIR/.local" "$HOME_DIR/.local/lib/node_modules" "$HOME_DIR/.local/bin" \
    "$HOME_DIR/.local/share" "$HOME_DIR/.dsh" "$HOME_DIR/.dsh/profiles" \
    "$APP_CONFIG" "$APP_DATA" "$LITELLM_CONFIG" "$OMNIROUTE_CONFIG" "$USER_UNITS" "$QUADLETS" \
    "$HOME_DIR/.dsh/profiles/web" "$APP_DATA/dsh-dashboard-launcher.py" "$READY_FILE"; do
    [ ! -L "$path" ] || fail "Refusing a symlinked application path: $path"
  done
  for file in "$USER_UNITS/dsh.service" "$USER_UNITS/opencode-web.service" \
    "$QUADLETS/litellm.pod" "$QUADLETS/litellm-postgres.volume" "$QUADLETS/litellm-db.container" "$QUADLETS/litellm.container" \
    "$QUADLETS/omniroute.pod" "$QUADLETS/omniroute-redis.volume" "$QUADLETS/omniroute-redis.container" "$QUADLETS/omniroute.container"; do
    [ ! -L "$file" ] || fail "Refusing a symlinked app unit path: $file"
  done
}

check_package_version() {
  package_dir=$1
  expected=$2
  label=$3
  if [ -f "$package_dir/package.json" ]; then
    actual=$(node -e 'process.stdout.write(require(process.argv[1]).version || "")' "$package_dir/package.json" 2>/dev/null || true)
    [ "$actual" = "$expected" ] || fail "$label is already installed at a different version ($actual); review it before replacement."
  fi
}

install_cli_packages() {
  mkdir -p "$HOME_DIR/.local/lib/node_modules" "$HOME_DIR/.local/bin" "$TOOLS_DIR"
  check_package_version "$HOME_DIR/.local/lib/node_modules/@deepseek-ai/dsh" "$DSH_VERSION" 'DeepSeek Harness'
  check_package_version "$HOME_DIR/.local/lib/node_modules/@agentclientprotocol/codex-acp" "$ACP_VERSION" 'Codex ACP'
  if [ ! -f "$HOME_DIR/.local/lib/node_modules/@deepseek-ai/dsh/package.json" ] || \
     [ ! -f "$HOME_DIR/.local/lib/node_modules/@agentclientprotocol/codex-acp/package.json" ]; then
    npm install --global --prefix "$HOME_DIR/.local" --no-audit --no-fund \
      --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs \
      "@deepseek-ai/dsh@$DSH_VERSION" "@agentclientprotocol/codex-acp@$ACP_VERSION"
  fi
  # npm 11 otherwise skips these pinned dependencies' native/helper install scripts.
  npm rebuild --global --prefix "$HOME_DIR/.local" --no-audit --no-fund \
    --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs \
    @deepseek-ai/dsh-subprocess-local koffi node-pty @google/genai protobufjs

  pnpm_pkg="$TOOLS_DIR/node_modules/pnpm/package.json"
  if [ -f "$pnpm_pkg" ]; then
    actual=$(node -e 'process.stdout.write(require(process.argv[1]).version)' "$pnpm_pkg")
    [ "$actual" = "$PNPM_VERSION" ] || fail "The playground's scoped pnpm runtime is $actual, expected $PNPM_VERSION."
  else
    npm install --prefix "$TOOLS_DIR" --no-audit --no-fund "pnpm@$PNPM_VERSION"
  fi
  PATH="$TOOLS_DIR/node_modules/.bin:$HOME_DIR/.local/bin:$PATH"
  export PATH
  [ "$("$HOME_DIR/.local/bin/dsh" --version 2>/dev/null)" = "$DSH_VERSION" ] || fail 'Installed DSH version did not match the pinned release.'
  "$HOME_DIR/.local/bin/codex-acp" --version >/dev/null
  [ "$(pnpm --version)" = "$PNPM_VERSION" ] || fail 'The scoped pnpm runtime did not start at its pinned version.'

  export HOME="$HOME_DIR" DSH_HOME="$HOME_DIR/.dsh" CODEX_HOME="$HOME_DIR/.codex"
  profile="$DSH_HOME/profiles/web/package.json"
  if [ -f "$profile" ]; then
    installed=$(node -e 'const p=require(process.argv[1]); process.stdout.write((p.dependencies||{})["@zaimokuza/dsh-acp-adapter"]||"")' "$profile")
    [ "$installed" = "$ADAPTER_VERSION" ] || fail "The existing DSH Web profile has a different ACP adapter spec ('$installed')."
  else
    "$HOME_DIR/.local/bin/dsh" plugin --profile web add "@zaimokuza/dsh-acp-adapter@$ADAPTER_VERSION"
  fi
  node - "$DSH_HOME/profiles/web/node_modules/@zaimokuza/dsh-acp-adapter/package.json" "$ADAPTER_VERSION" <<'NODE'
const fs = require("node:fs");
const actual = JSON.parse(fs.readFileSync(process.argv[2], "utf8")).version;
if (actual !== process.argv[3]) process.exit(1);
NODE
  "$HOME_DIR/.local/bin/dsh" --profile web --dump-config >/dev/null 2>&1 || fail 'DSH Web profile could not load its pinned plugin composition.'
}

check_acp_initialize() {
  python3 - "$HOME_DIR/.local/bin/codex-acp" "$HOME_DIR/.opencode/bin/opencode" <<'PY'
import json, select, subprocess, sys, time
request = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"huou07-readiness","version":"1"}}}) + "\n"
agents = (([sys.argv[1]], "Codex ACP"), ([sys.argv[2], "acp"], "OpenCode ACP"))
for command, label in agents:
    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, bufsize=1)
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(request)
        process.stdin.flush()
        deadline = time.monotonic() + 45
        response = None
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 1)
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            try:
                item = json.loads(line)
                if item.get("id") == 1:
                    response = item
                    break
            except json.JSONDecodeError:
                pass
        if not response or "error" in response or "result" not in response:
            raise RuntimeError
    except Exception:
        print(f"{label} ACP initialize failed (no model request was sent).", file=sys.stderr)
        raise SystemExit(1)
    finally:
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.close()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.terminate()
                process.wait(timeout=5)
            for stream in (process.stdout, process.stderr):
                if stream:
                    stream.close()
    print(f"{label} ACP initialize passed (no model request was sent).")
PY
}

ensure_config_files() {
  mkdir -p "$APP_CONFIG" "$LITELLM_CONFIG" "$OMNIROUTE_CONFIG" "$APP_DATA" "$HOME_DIR/Projects"
  chmod 0700 "$APP_CONFIG" "$LITELLM_CONFIG" "$OMNIROUTE_CONFIG" "$APP_DATA"
  if [ ! -f "$APP_CONFIG/opencode-web.env" ]; then
    pass=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    write_secret_file "$APP_CONFIG/opencode-web.env" "OPENCODE_SERVER_USERNAME=opencode" "OPENCODE_SERVER_PASSWORD=$pass"
    unset pass
  fi
  if [ ! -f "$LITELLM_CONFIG/postgres.env" ]; then
    pgpass=$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')
    write_secret_file "$LITELLM_CONFIG/postgres.env" "POSTGRES_DB=litellm" "POSTGRES_USER=litellm" "POSTGRES_PASSWORD=$pgpass"
    unset pgpass
  fi
  if [ ! -f "$LITELLM_CONFIG/litellm.env" ]; then
    master=$(python3 -c 'import secrets; print("sk-" + secrets.token_hex(32))')
    salt=$(python3 -c 'import secrets; print("sk-" + secrets.token_hex(32))')
    dbpass=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$LITELLM_CONFIG/postgres.env")
    [ -n "$dbpass" ] || fail 'The PostgreSQL password file is incomplete.'
    write_secret_file "$LITELLM_CONFIG/litellm.env" \
      "LITELLM_MASTER_KEY=$master" "LITELLM_SALT_KEY=$salt" \
      "DATABASE_URL=postgresql://litellm:$dbpass@127.0.0.1:5432/litellm" "STORE_MODEL_IN_DB=True"
    unset master salt dbpass
  fi
  if [ ! -f "$OMNIROUTE_CONFIG/omniroute.env" ]; then
    password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    jwt=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    api_key_secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    ws_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    write_secret_file "$OMNIROUTE_CONFIG/omniroute.env" \
      'DASHBOARD_PORT=20128' 'API_PORT=20129' 'LIVE_WS_PORT=20132' \
      'DATA_DIR=/app/data' 'REDIS_URL=redis://127.0.0.1:6379' 'REQUIRE_API_KEY=true' \
      "INITIAL_PASSWORD=$password" "JWT_SECRET=$jwt" "API_KEY_SECRET=$api_key_secret" \
      "OMNIROUTE_WS_BRIDGE_SECRET=$ws_secret" 'OMNIROUTE_MEMORY_MB=2048'
    unset password jwt api_key_secret ws_secret
  fi
  if [ ! -f "$LITELLM_CONFIG/config.yaml" ]; then
    umask 077
    printf 'model_list: []\n' > "$LITELLM_CONFIG/config.yaml"
    chmod 0600 "$LITELLM_CONFIG/config.yaml"
  fi
  for file in "$APP_CONFIG/opencode-web.env" "$LITELLM_CONFIG/postgres.env" "$LITELLM_CONFIG/litellm.env" "$OMNIROUTE_CONFIG/omniroute.env"; do
    [ -f "$file" ] && [ ! -L "$file" ] || fail "Required application configuration is missing or symlinked: $file"
    [ "$(stat -c '%a' "$file")" = 600 ] || fail "Secret file must have mode 0600: $file"
  done
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

install_unit_files() {
  mkdir -p "$USER_UNITS" "$QUADLETS"
  install_or_verify() {
    source=$1
    target=$2
    if [ -e "$target" ]; then
      [ -f "$target" ] && [ ! -L "$target" ] || fail "Existing application file is not a regular file: $target"
      if ! cmp -s "$source" "$target"; then
        install -m 0644 "$source" "$target"
      fi
    else
      install -m 0644 "$source" "$target"
    fi
  }
  install_or_verify "$ROOT/deploy/dsh-dashboard-launcher.py" "$APP_DATA/dsh-dashboard-launcher.py"
  for pair in \
    "deploy/user/dsh.service:$USER_UNITS/dsh.service" \
    "deploy/user/opencode-web.service:$USER_UNITS/opencode-web.service" \
    "deploy/user/litellm.pod:$QUADLETS/litellm.pod" \
    "deploy/user/litellm-postgres.volume:$QUADLETS/litellm-postgres.volume" \
    "deploy/user/litellm-db.container:$QUADLETS/litellm-db.container" \
    "deploy/user/litellm.container:$QUADLETS/litellm.container" \
    "deploy/user/omniroute.pod:$QUADLETS/omniroute.pod" \
    "deploy/user/omniroute-redis.volume:$QUADLETS/omniroute-redis.volume" \
    "deploy/user/omniroute-redis.container:$QUADLETS/omniroute-redis.container" \
    "deploy/user/omniroute.container:$QUADLETS/omniroute.container"; do
    source=${pair%%:*}
    target=${pair#*:}
    install_or_verify "$ROOT/$source" "$target"
  done
}

validate_quadlets() {
  temp=$(mktemp -d "$APP_DATA/quadlet-check.XXXXXX")
  trap 'rm -rf "$temp"' EXIT HUP INT TERM
  cp "$QUADLETS"/*.pod "$QUADLETS"/*.volume "$QUADLETS"/*.container "$temp/"
  if ! QUADLET_UNIT_DIRS="$temp" /usr/lib/systemd/system-generators/podman-system-generator --user --dryrun >"$temp/output" 2>&1; then
    sed -n '/error\|failed\|Error\|Failed/p' "$temp/output" >&2
    fail 'Podman Quadlet generation failed before cutover.'
  fi
  for unit in litellm-pod.service litellm-postgres-volume.service litellm-db.service litellm.service \
    omniroute-pod.service omniroute-redis-volume.service omniroute-redis.service omniroute.service; do
    grep -q -- "---$unit---" "$temp/output" || fail "Quadlet generator did not produce $unit."
  done
  if grep -Eiq 'error loading|failed to parse|invalid quadlet|unknown key' "$temp/output"; then
    sed -n '/error\|failed\|Error\|Failed/p' "$temp/output" >&2
    fail 'Podman Quadlet parser reported an invalid unit.'
  fi
  trap - EXIT HUP INT TERM
  rm -rf "$temp"
  printf 'Podman 5.4 Quadlet generation passed for all eight units.\n'
}

pull_images() {
  for image in "$LITELLM_IMAGE" "$POSTGRES_IMAGE" "$OMNIROUTE_IMAGE" "$REDIS_IMAGE"; do
    if ! podman image exists "$image"; then
      podman pull "$image"
    else
      printf 'Image ready: %s\n' "$image"
    fi
  done
}

write_readiness_marker() {
  commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf unknown)
  python3 - "$READY_FILE" "$commit" "$DSH_VERSION" "$ACP_VERSION" "$ADAPTER_VERSION" "$LITELLM_IMAGE" "$OMNIROUTE_IMAGE" <<'PY'
import json, os, sys, tempfile
path, commit, dsh, codex_acp, adapter, litellm, omniroute = sys.argv[1:]
data = {"commit": commit, "dsh": dsh, "codex_acp": codex_acp, "adapter": adapter, "litellm_image": litellm, "omniroute_image": omniroute}
fd, temporary = tempfile.mkstemp(prefix=".readiness-", dir=os.path.dirname(path))
try:
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary): os.unlink(temporary)
PY
}

prepare() {
  check_identity
  check_clean_inputs
  mkdir -p "$APP_DATA" "$HOME_DIR/Projects"
  export HOME="$HOME_DIR" DSH_HOME="$HOME_DIR/.dsh" CODEX_HOME="$HOME_DIR/.codex"
  if login_status=$("$HOME_DIR/.local/bin/codex" login status 2>&1) && printf '%s' "$login_status" | grep -qi 'logged in using chatgpt'; then
    printf 'Native Codex ChatGPT login detected (credentials hidden).\n'
  else
    printf 'OWNER_LOGIN_REQUIRED: native Codex CLI is not signed in.\n'
  fi
  if "$HOME_DIR/.opencode/bin/opencode" auth list >/dev/null 2>&1; then
    printf 'Native OpenCode authentication state is readable by its CLI (values hidden).\n'
  else
    printf 'OWNER_LOGIN_REQUIRED: OpenCode provider sign-in may be needed.\n'
  fi
  install_cli_packages
  check_acp_initialize
  ensure_config_files
  install_unit_files
  validate_quadlets
  pull_images
  python3 "$ROOT/deploy/check-user-app-runtime.py"
  write_readiness_marker
  printf 'READY: packages, ACP initialize, owner config, Quadlets, images, and fresh container UI/persistence checks passed. Legacy services were not stopped.\n'
}

check_readiness_marker() {
  [ -f "$READY_FILE" ] && [ ! -L "$READY_FILE" ] || fail 'Readiness marker missing; run prepare from this checkout before activation.'
  commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf unknown)
  python3 - "$READY_FILE" "$commit" "$DSH_VERSION" "$ACP_VERSION" "$ADAPTER_VERSION" "$LITELLM_IMAGE" "$OMNIROUTE_IMAGE" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
expected = dict(zip(("commit", "dsh", "codex_acp", "adapter", "litellm_image", "omniroute_image"), sys.argv[2:]))
if data != expected:
    print("Prepared state does not match this checkout and its pinned software versions.", file=sys.stderr)
    raise SystemExit(1)
PY
  [ -f "$HOME_DIR/.local/bin/dsh" ] && [ -f "$HOME_DIR/.local/bin/codex-acp" ] || fail 'Prepared CLI packages are missing.'
  for image in "$LITELLM_IMAGE" "$POSTGRES_IMAGE" "$OMNIROUTE_IMAGE" "$REDIS_IMAGE"; do
    podman image exists "$image" || fail "Prepared container image is missing: $image"
  done
  for file in "$APP_CONFIG/opencode-web.env" "$LITELLM_CONFIG/postgres.env" "$LITELLM_CONFIG/litellm.env" "$OMNIROUTE_CONFIG/omniroute.env"; do
    [ -f "$file" ] && [ ! -L "$file" ] || fail "Prepared application configuration is missing: $file"
  done
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
    print("After legacy retirement, ports still occupied: " + ", ".join(map(str, busy)), file=sys.stderr)
    raise SystemExit(1)
PY
}

activate() {
  check_identity
  check_readiness_marker
  ports_free
  systemctl --user daemon-reload
  systemctl --user enable --now dsh.service opencode-web.service
  # Quadlet's generator applies [Install] on reload; generated units cannot be enabled directly.
  systemctl --user start litellm.service omniroute.service
  status
}

wait_for_http() {
  python3 "$ROOT/deploy/check-user-app-health.py" \
    --opencode-env "$APP_CONFIG/opencode-web.env" \
    --dsh-token-file /run/huou07-dsh-link/url
}

status() {
  check_identity
  for unit in dsh.service opencode-web.service litellm-pod.service litellm-postgres-volume.service litellm-db.service litellm.service \
    omniroute-pod.service omniroute-redis-volume.service omniroute-redis.service omniroute.service; do
    systemctl --user is-active --quiet "$unit" || fail "User service is not active: $unit"
  done
  wait_for_http
  printf 'All new application units and local health checks passed.\n'
}

deactivate() {
  check_identity
  systemctl --user show-environment >/dev/null 2>&1 || fail 'The huou07 systemd user manager is unavailable.'
  hold="$APP_DATA/rollback/containers-systemd"
  [ ! -e "$hold" ] && [ ! -L "$hold" ] || fail "Rollback holding path already exists: $hold"
  for unit in dsh.service opencode-web.service litellm.service litellm-db.service litellm-postgres-volume.service \
    litellm-pod.service omniroute.service omniroute-redis.service omniroute-redis-volume.service omniroute-pod.service; do
    state=$(systemctl --user show --property=LoadState --property=ActiveState --value "$unit") || fail "Could not inspect user unit: $unit"
    load_state=$(printf '%s\n' "$state" | sed -n '1p')
    active_state=$(printf '%s\n' "$state" | sed -n '2p')
    if [ "$load_state" = not-found ] && [ "$active_state" = inactive ]; then
      continue
    fi
    [ "$load_state" = loaded ] || fail "Unexpected load state for $unit: $load_state"
    systemctl --user stop "$unit" || fail "Could not stop fresh application unit: $unit"
    systemctl --user reset-failed "$unit" >/dev/null 2>&1 || true
    state=$(systemctl --user show --property=LoadState --property=ActiveState --value "$unit") || fail "Could not verify stopped unit: $unit"
    [ "$(printf '%s\n' "$state" | sed -n '1p')" = loaded ] && \
      [ "$(printf '%s\n' "$state" | sed -n '2p')" = inactive ] || fail "Fresh application unit is not confirmed inactive: $unit"
  done
  for name in huou07-litellm-db huou07-litellm-proxy huou07-omniroute huou07-omniroute-redis; do
    if podman container exists "$name"; then
      running=$(podman inspect --format '{{.State.Running}}' "$name") || fail "Could not inspect container: $name"
      [ "$running" = false ] || fail "Fresh application container is still running: $name"
    else
      result=$?
      [ "$result" -eq 1 ] || fail "Could not verify container state: $name"
    fi
  done
  for file in "$QUADLETS"/litellm.pod "$QUADLETS"/litellm-postgres.volume "$QUADLETS"/litellm-db.container \
    "$QUADLETS"/litellm.container "$QUADLETS"/omniroute.pod "$QUADLETS"/omniroute-redis.volume \
    "$QUADLETS"/omniroute-redis.container "$QUADLETS"/omniroute.container; do
    [ ! -L "$file" ] || fail "Refusing to move a symlinked Quadlet: $file"
    [ ! -e "$file" ] || [ -f "$file" ] || fail "Quadlet is not a regular file: $file"
  done
  systemctl --user disable dsh.service opencode-web.service >/dev/null || fail 'Could not disable fresh Web services.'
  mkdir -m 0700 -p "$hold"
  for file in "$QUADLETS"/litellm.pod "$QUADLETS"/litellm-postgres.volume "$QUADLETS"/litellm-db.container \
    "$QUADLETS"/litellm.container "$QUADLETS"/omniroute.pod "$QUADLETS"/omniroute-redis.volume \
    "$QUADLETS"/omniroute-redis.container "$QUADLETS"/omniroute.container; do
    [ ! -e "$file" ] || mv -- "$file" "$hold/"
  done
  systemctl --user daemon-reload
  printf 'Fresh applications are stopped. Their Quadlets are held at %s; application data remains intact.\n' "$hold"
  printf 'The previous system units can now be restored by the owner.\n'
}

case "$ACTION" in
  prepare) prepare ;;
  activate) activate ;;
  status) status ;;
  deactivate) deactivate ;;
  *) fail 'Usage: deploy/install-user-apps.sh [prepare|activate|status|deactivate]' ;;
esac
