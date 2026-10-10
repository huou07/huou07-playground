#!/usr/bin/env bash
# Owner-run cutover. preflight is read-only; cutover is the only phase that stops services.
set -Eeuo pipefail
cd /
ACTION=${1:-}
case "$ACTION" in preflight|cutover|rollback) ;; *) echo "usage: $0 preflight|cutover|rollback" >&2; exit 2;; esac
[[ $EUID == 0 ]] || { echo "Run as root; this script never invokes sudo." >&2; exit 1; }

USER_NAME=huou07
HOME_DIR=/home/huou07
BACKUP_ROOT=/var/backups/huou07-one-user
RECORD=/var/lib/huou07-playground-migration/active-backup
PG_VOLUME=huou07-litellm-postgres
REPO=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
RUNTIME=/run/user/$(id -u "$USER_NAME")
SYSTEM_UNITS=(huou07-dsh.service huou07-opencode-web.service huou07-litellm.service huou07-litellm-db.service huou07-omniroute.service huou07-playground.service)
USER_UNITS=(huou07-playground.service huou07-dsh.service huou07-opencode-web.service huou07-omniroute.service huou07-litellm.service huou07-litellm-db.service)
fail() { echo "Migration stopped: $*" >&2; exit 1; }
as_user() { runuser -u "$USER_NAME" -- env HOME="$HOME_DIR" XDG_RUNTIME_DIR="$RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" "$@"; }
as_service() { local user=$1 home=$2 runtime=$3; shift 3; runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="$runtime" "$@"; }
userctl() { as_user /usr/bin/systemctl --user "$@"; }

preflight() {
  [[ $(getent passwd "$USER_NAME" | cut -d: -f6) == "$HOME_DIR" ]] || fail "unexpected target HOME"
  [[ $(loginctl show-user "$USER_NAME" -p Linger --value) == yes ]] || fail "lingering must remain enabled"
  [[ -S $RUNTIME/bus ]] || fail "huou07 user-manager bus unavailable"
  [[ -x /home/huou07/.local/bin/codex && -x "$HOME_DIR/.opencode/bin/opencode" ]] || fail "native Codex/OpenCode CLI missing"
  [[ -x /usr/local/libexec/huou07-litellm/prepare.sh && -x /usr/local/libexec/huou07-omniroute/prepare.sh ]] || fail "rootless service helpers missing"
  [[ -x /usr/bin/podman && -x /usr/bin/slirp4netns ]] || fail "rootless Podman dependencies missing"
  grep -q '^huou07:' /etc/subuid || fail "huou07 has no subordinate UID range for rootless Podman"
  grep -q '^huou07:' /etc/subgid || fail "huou07 has no subordinate GID range for rootless Podman"
  local login
  login=$(as_user /home/huou07/.local/bin/codex login status 2>&1) || fail "Codex login status could not be checked"
  [[ $login == *"Logged in using ChatGPT"* ]] || fail "native Codex ChatGPT login is not present; refusing to alter auth"
  for unit in "${SYSTEM_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" || fail "expected production unit is not active: $unit"
    if userctl is-active --quiet "$unit"; then fail "target user unit is already active: $unit"; fi
    if [[ -e $HOME_DIR/.config/systemd/user/$unit ]]; then fail "target unit file already exists; refusing to replace it: $unit"; fi
  done
  local dsh_port
  dsh_port=$(python3 "$REPO/web/private_services.py" --port dsh backend_port) || fail "DSH port configuration could not be read"
  curl -fsS --max-time 3 http://127.0.0.1:4000/health/liveliness >/dev/null || fail "production LiteLLM health check failed"
  curl -fsS --max-time 3 http://127.0.0.1:20128/healthz >/dev/null || fail "production OmniRoute health check failed"
  curl -fsS --max-time 3 "http://127.0.0.1:$dsh_port/favicon.svg" >/dev/null || fail "production DSH health check failed"
  local opencode_status
  opencode_status=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:4096/) || fail "production OpenCode Web health check failed"
  [[ $opencode_status == 200 || $opencode_status == 401 || $opencode_status == 403 ]] || fail "production OpenCode Web HTTP $opencode_status"
  curl -fsS --max-time 3 http://127.0.0.1:8765/api/health >/dev/null || fail "production dashboard health check failed"
  [[ -d /var/lib/huou07-dsh/dsh/profiles/web ]] || fail "DSH web profile/session tree missing"
  [[ -d /var/lib/huou07-opencode/data ]] || fail "OpenCode native data tree missing"
  local source_auth
  source_auth=$(find /var/lib/huou07-opencode/data -xdev -type f -name auth.json -print -quit) || fail "OpenCode credential discovery failed"
  [[ -n $source_auth ]] || fail "OpenCode Web provider auth.json missing"
  echo "OpenCode credential source path: $source_auth (contents not read)"
  [[ -f /etc/huou07-playground/opencode-web.env && -f /var/lib/huou07-playground/apps.json ]] || fail "OpenCode Web auth or dashboard registry missing"
  [[ -f /etc/huou07-litellm/config.yaml && -f /etc/huou07-litellm/litellm.env && -f /etc/huou07-litellm/postgres.env ]] || fail "LiteLLM state missing"
  [[ -f /etc/huou07-omniroute/omniroute.env && -d /var/lib/huou07-omniroute/data ]] || fail "OmniRoute state missing"
  as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm /usr/bin/podman info --format '{{.Host.Security.Rootless}}' | grep -qx true || fail "LiteLLM Podman discovery failed"
  as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm /usr/bin/podman volume exists "$PG_VOLUME" || fail "LiteLLM PostgreSQL volume missing"
  as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute /usr/bin/podman info --format '{{.Host.Security.Rootless}}' | grep -qx true || fail "OmniRoute Podman discovery failed"
  local mapped_owner
  mapped_owner=$(as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute /usr/bin/podman unshare stat -c '%u:%g' /var/lib/huou07-omniroute/data) || fail "OmniRoute namespace ownership could not be read"
  [[ $mapped_owner == 1000:1000 ]] || fail "OmniRoute data owner maps to $mapped_owner in its original namespace, expected 1000:1000"
  as_user /usr/bin/podman info --format '{{.Host.Security.Rootless}}' | grep -qx true || fail "target rootless Podman unavailable"
  local volume_rc=0
  as_user /usr/bin/podman volume exists "$PG_VOLUME" || volume_rc=$?
  [[ $volume_rc == 1 ]] || fail "target PostgreSQL volume check returned $volume_rc (expected 1=absent)"
  if [[ -S /run/docker.sock ]] && getent group docker | awk -F: '$4 ~ /(^|,)huou07(,|$)/{found=1} END{exit !found}'; then
    fail "rootful Docker socket is present and huou07 has docker-group access; resolve before enabling agents"
  fi
  local sudo_listing
  sudo_listing=$(mktemp)
  /usr/bin/sudo -n -l -U huou07 >"$sudo_listing" 2>&1 || fail "could not verify huou07 sudo policy"
  if grep -Eiq 'NOPASSWD|!authenticate' "$sudo_listing"; then rm -f "$sudo_listing"; fail "passwordless sudo is configured for huou07"; fi
  rm -f "$sudo_listing"
  local target_uid
  target_uid=$(id -u "$USER_NAME")
  for path in "$HOME_DIR/Projects" "$HOME_DIR/.config" "$HOME_DIR/.local" "$HOME_DIR/.local/share" "$HOME_DIR/.local/state" "$HOME_DIR/.cache" "$HOME_DIR/.config/systemd/user"; do
    if [[ -L $path ]]; then fail "target path is a symlink; refusing path redirection: $path"; fi
    if [[ -e $path ]]; then
      [[ -d $path && $(stat -c '%u' "$path") == "$target_uid" ]] || fail "target directory must be an ordinary huou07-owned directory: $path"
    fi
  done
  for path in "$HOME_DIR/Projects/dsh" "$HOME_DIR/Projects/opencode" "$HOME_DIR/.config/litellm" "$HOME_DIR/.config/omniroute" "$HOME_DIR/.local/share/omniroute/data"; do
    if [[ -e $path ]]; then local contents; contents=$(find "$path" -mindepth 1 -maxdepth 1 -print) || fail "could not inspect $path"; [[ -z $contents ]] || fail "target path is not empty: $path"; fi
  done
  [[ ! -e $HOME_DIR/.dsh && ! -L $HOME_DIR/.dsh ]] || fail "destination exists; refusing to merge DSH profile/session tree: $HOME_DIR/.dsh"
  verify_merge /var/lib/huou07-dsh/config "$HOME_DIR/.config"
  verify_merge /var/lib/huou07-dsh/data "$HOME_DIR/.local/share"
  verify_merge /var/lib/huou07-dsh/state "$HOME_DIR/.local/state"
  verify_merge /var/lib/huou07-dsh/cache "$HOME_DIR/.cache"
  verify_merge /var/lib/huou07-opencode/config "$HOME_DIR/.config"
  verify_merge /var/lib/huou07-opencode/data "$HOME_DIR/.local/share"
  verify_merge /var/lib/huou07-opencode/state "$HOME_DIR/.local/state"
  verify_merge /var/lib/huou07-opencode/cache "$HOME_DIR/.cache"
  verify_merge /srv/huou07-dsh-workspaces "$HOME_DIR/Projects/dsh"
  verify_merge /srv/huou07-opencode-workspaces "$HOME_DIR/Projects/opencode"
  for path in "$HOME_DIR/.config/opencode/web.env" "$HOME_DIR/.local/state/huou07-playground/apps.json"; do
    [[ ! -e $path ]] || fail "destination exists; refusing to replace owner data: $path"
  done
  [[ ! -e /srv/huou07-dsh-workspaces-legacy && ! -e /srv/huou07-opencode-workspaces-legacy ]] || fail "workspace rollback destination exists"
  [[ -d /srv/huou07-dsh-workspaces && -d /srv/huou07-opencode-workspaces ]] || fail "legacy workspaces missing"
  for unit in "${SYSTEM_UNITS[@]}"; do
    state=$(systemctl is-enabled "$unit" 2>/dev/null || true)
    [[ $state == enabled || $state == enabled-runtime || $state == disabled || $state == static || $state == indirect || $state == generated ]] || fail "unsupported original unit enable state for $unit: ${state:-unknown}"
  done
  echo 'Preflight passed. It did not stop or restart any service.'
}

copy_merge() {
  local src=$1 dst=$2 item rel target
  [[ -d $src ]] || return 0
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$dst"
  find "$src" -mindepth 1 -xdev -print0 | while IFS= read -r -d '' item; do
    rel=${item#"$src"/}; target=$dst/$rel
    if [[ -e $target || -L $target ]]; then
      if [[ -d $item && -d $target && ! -L $item && ! -L $target ]]; then continue
      elif [[ -L $item && -L $target && $(readlink "$item") == "$(readlink "$target")" ]]; then continue
      elif [[ -f $item && -f $target ]] && cmp -s "$item" "$target"; then continue
      else fail "state collision; no destination was overwritten: $target"; fi
    fi
    if [[ -d $item && ! -L $item ]]; then install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$target"
    else install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$(dirname "$target")"; cp -a --no-preserve=ownership "$item" "$target"; chown -h "$USER_NAME:$USER_NAME" "$target"; fi
  done
}

verify_merge() {
  local src=$1 dst=$2 item rel target
  [[ -d $src ]] || return 0
  find "$src" -mindepth 1 -xdev -print0 | while IFS= read -r -d '' item; do
    rel=${item#"$src"/}; target=$dst/$rel
    if [[ -e $target || -L $target ]]; then
      if [[ -d $item && -d $target && ! -L $item && ! -L $target ]]; then continue
      elif [[ -L $item && -L $target && $(readlink "$item") == "$(readlink "$target")" ]]; then continue
      elif [[ -f $item && -f $target ]] && cmp -s "$item" "$target"; then continue
      else fail "state collision before cutover; destination will not be overwritten: $target"; fi
    fi
  done
}

stop_target() { for unit in "${USER_UNITS[@]}"; do userctl disable --now "$unit" >/dev/null 2>&1 || :; done; }
restore_legacy() {
  stop_target
  for unit in "${USER_UNITS[@]}"; do rm -f "$HOME_DIR/.config/systemd/user/$unit"; done
  userctl daemon-reload >/dev/null 2>&1 || :
  for base in dsh opencode; do
    old=/srv/huou07-$base-workspaces; legacy=$old-legacy
    if [[ -L $old && -d $legacy ]]; then rm -- "$old"; mv -- "$legacy" "$old"; fi
  done
  if [[ -f ${backup:-}/dsh-policy.js && -f ${backup:-}/dsh-picker.js ]]; then
    install -o root -g root -m 0644 "$backup/dsh-policy.js" /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-sandbox-policy/lib/index.js
    install -o root -g root -m 0644 "$backup/dsh-picker.js" /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-host-directory-picker-browse/lib/index.js
  fi
  if [[ -f ${backup:-}/system-unit-states ]]; then
    while read -r unit state; do
      case "$state" in enabled|enabled-runtime) systemctl enable "$unit" >/dev/null;; *) systemctl disable "$unit" >/dev/null 2>&1 || :;; esac
    done < "$backup/system-unit-states"
  fi
  systemctl start "${SYSTEM_UNITS[@]}"
  for unit in "${SYSTEM_UNITS[@]}"; do systemctl is-active --quiet "$unit" || fail "legacy unit did not recover: $unit"; done
  rm -f "$RECORD"
}

if [[ $ACTION == preflight ]]; then
  preflight
  echo 'Review this exact command before any cutover: sudo sh deploy/migrate-one-user.sh cutover'
  exit 0
fi

if [[ $ACTION == rollback ]]; then
  [[ -f $RECORD ]] || fail "migration backup record not found"
  backup=$(cat "$RECORD")
  [[ -f $backup/dsh-policy.js && -f $backup/dsh-picker.js ]] || fail "rollback backup incomplete"
  restore_legacy
  echo 'Legacy services are restored against their untouched original data. New HOME data and backups remain in place.'
  exit 0
fi

preflight
[[ ! -e $RECORD && ! -L $RECORD ]] || fail "an existing migration record requires explicit review: $RECORD"
install -d -o root -g root -m 0700 "$BACKUP_ROOT" /var/lib/huou07-playground-migration
stamp=$(date -u +%Y%m%dT%H%M%SZ); backup=$BACKUP_ROOT/$stamp; mkdir -m 0700 "$backup"
printf '%s\n' "$backup" > "$RECORD"; chmod 0600 "$RECORD"
did_stop=0
cutover_success=0
on_exit() {
  status=$?
  trap - EXIT
  if ((did_stop && !cutover_success)); then echo 'Cutover failed; restoring original services.' >&2; restore_legacy || :; fi
  if (( ! cutover_success )); then echo "Private recovery data retained at $backup" >&2; fi
  exit "$status"
}
trap on_exit EXIT

for unit in "${SYSTEM_UNITS[@]}"; do printf '%s %s\n' "$unit" "$(systemctl is-enabled "$unit" 2>/dev/null || true)"; done > "$backup/system-unit-states"
chmod 0600 "$backup/system-unit-states"

# This explicit cutover command is the first operation that stops production.
did_stop=1
for unit in huou07-playground.service huou07-dsh.service huou07-opencode-web.service huou07-omniroute.service huou07-litellm.service huou07-litellm-db.service; do systemctl stop "$unit"; done
source_paths=(var/lib/huou07-dsh var/lib/huou07-opencode var/lib/huou07-playground/apps.json var/lib/huou07-omniroute/data etc/huou07-playground etc/huou07-litellm etc/huou07-omniroute srv/huou07-dsh-workspaces srv/huou07-opencode-workspaces home/huou07/.codex home/huou07/.config/opencode home/huou07/.local/share/opencode home/huou07/.local/state/opencode home/huou07/.cache/opencode)
present=(); for path in "${source_paths[@]}"; do [[ ! -e /$path ]] || present+=("$path"); done
tar --numeric-owner --acls --xattrs -cpf "$backup/state.tar" -C / "${present[@]}"; chmod 0600 "$backup/state.tar"
cp /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-sandbox-policy/lib/index.js "$backup/dsh-policy.js"
cp /opt/huou07-dsh/app/node_modules/@deepseek-ai/dsh-host-directory-picker-browse/lib/index.js "$backup/dsh-picker.js"
chmod 0600 "$backup/dsh-policy.js" "$backup/dsh-picker.js"
as_service huou07-litellm /var/lib/huou07-litellm /run/huou07-litellm /usr/bin/podman volume export "$PG_VOLUME" > "$backup/litellm-postgres-volume.tar"
chmod 0600 "$backup/litellm-postgres-volume.tar"
as_service huou07-omniroute /var/lib/huou07-omniroute /run/huou07-omniroute /usr/bin/podman unshare tar --numeric-owner -cpf - -C /var/lib/huou07-omniroute/data . > "$backup/omniroute-data.tar"
chmod 0600 "$backup/omniroute-data.tar"
  while read -r unit state; do
    case "$state" in enabled|enabled-runtime) systemctl disable "$unit";; esac
  done < "$backup/system-unit-states"

install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$HOME_DIR/Projects" "$HOME_DIR/.config" "$HOME_DIR/.local/share" "$HOME_DIR/.local/state" "$HOME_DIR/.cache" "$HOME_DIR/.dsh"
copy_merge /var/lib/huou07-dsh/dsh "$HOME_DIR/.dsh"
copy_merge /var/lib/huou07-dsh/config "$HOME_DIR/.config"
copy_merge /var/lib/huou07-dsh/data "$HOME_DIR/.local/share"
copy_merge /var/lib/huou07-dsh/state "$HOME_DIR/.local/state"
copy_merge /var/lib/huou07-dsh/cache "$HOME_DIR/.cache"
copy_merge /var/lib/huou07-opencode/config "$HOME_DIR/.config"
copy_merge /var/lib/huou07-opencode/data "$HOME_DIR/.local/share"
copy_merge /var/lib/huou07-opencode/state "$HOME_DIR/.local/state"
copy_merge /var/lib/huou07-opencode/cache "$HOME_DIR/.cache"
copy_merge /srv/huou07-dsh-workspaces "$HOME_DIR/Projects/dsh"
copy_merge /srv/huou07-opencode-workspaces "$HOME_DIR/Projects/opencode"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$HOME_DIR/.config/litellm" "$HOME_DIR/.config/omniroute" "$HOME_DIR/.local/share/omniroute/data" "$HOME_DIR/.local/state/huou07-playground"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-litellm/litellm.env "$HOME_DIR/.config/litellm/litellm.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-litellm/postgres.env "$HOME_DIR/.config/litellm/postgres.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0644 /etc/huou07-litellm/config.yaml "$HOME_DIR/.config/litellm/config.yaml"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-omniroute/omniroute.env "$HOME_DIR/.config/omniroute/omniroute.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /etc/huou07-playground/opencode-web.env "$HOME_DIR/.config/opencode/web.env"
install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /var/lib/huou07-playground/apps.json "$HOME_DIR/.local/state/huou07-playground/apps.json"

as_user /usr/bin/podman volume create "$PG_VOLUME" >/dev/null
as_user /usr/bin/podman volume import "$PG_VOLUME" - < "$backup/litellm-postgres-volume.tar"
as_user /usr/bin/podman unshare tar --numeric-owner --same-owner -xpf "$backup/omniroute-data.tar" -C "$HOME_DIR/.local/share/omniroute/data"
target_owner=$(as_user /usr/bin/podman unshare stat -c '%u:%g' "$HOME_DIR/.local/share/omniroute/data")
[[ $target_owner == 1000:1000 ]] || fail "imported OmniRoute owner is $target_owner, expected 1000:1000"
as_user /usr/bin/podman pull docker.io/library/postgres:16 >/dev/null
as_user /usr/bin/podman pull ghcr.io/berriai/litellm:v1.103.1 >/dev/null
as_user /usr/bin/podman pull docker.io/library/redis:8.6.5-alpine >/dev/null
as_user /usr/bin/podman pull docker.io/diegosouzapw/omniroute:3.8.51 >/dev/null

mv /srv/huou07-dsh-workspaces /srv/huou07-dsh-workspaces-legacy
ln -s "$HOME_DIR/Projects/dsh" /srv/huou07-dsh-workspaces
mv /srv/huou07-opencode-workspaces /srv/huou07-opencode-workspaces-legacy
ln -s "$HOME_DIR/Projects/opencode" /srv/huou07-opencode-workspaces
python3 "$REPO/deploy/patch_dsh_workspace_policy.py" apply
python3 "$REPO/deploy/patch_dsh_directory_picker.py" apply
install -o root -g root -m 0755 "$REPO/deploy/user/dsh-launcher.py" /usr/local/libexec/huou07-dsh/user-launcher.py
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$HOME_DIR/.config/systemd/user"
for file in "$REPO"/deploy/user/*.service; do install -o "$USER_NAME" -g "$USER_NAME" -m 0644 "$file" "$HOME_DIR/.config/systemd/user/$(basename "$file")"; done
userctl daemon-reload
userctl enable "${USER_UNITS[@]}"
userctl start huou07-litellm-db.service huou07-litellm.service huou07-omniroute.service huou07-opencode-web.service huou07-dsh.service

port=$(python3 "$REPO/web/private_services.py" --port dsh backend_port)
ready=0
for _ in $(seq 1 180); do
  if curl -fsS --max-time 2 http://127.0.0.1:4000/health/liveliness >/dev/null 2>&1 && curl -fsS --max-time 2 http://127.0.0.1:20128/healthz >/dev/null 2>&1 && curl -fsS --max-time 2 "http://127.0.0.1:$port/favicon.svg" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ $ready == 1 ]] || fail 'LiteLLM, OmniRoute, or DSH health check did not pass'
opencode_status=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:4096/)
[[ $opencode_status == 200 || $opencode_status == 401 || $opencode_status == 403 ]] || fail "OpenCode Web HTTP $opencode_status"
userctl start huou07-playground.service
curl -fsS --max-time 3 http://127.0.0.1:8765/api/health >/dev/null
userctl is-active huou07-playground.service >/dev/null
userctl is-enabled huou07-playground.service >/dev/null
main_pid=$(userctl show -p MainPID --value huou07-playground.service)
[[ $(ps -o user= -p "$main_pid" | xargs) == "$USER_NAME" ]] || fail 'dashboard process is not owned by huou07'

cutover_success=1
trap - EXIT
echo "Cutover passed local health checks. Private backup: $backup"
echo 'Original accounts, service homes, PostgreSQL volume, source app data, and units are retained; legacy units are stopped.'
echo 'No provider/model request was made. Verify sign-ins and persistence; do not clean legacy state without separate owner approval.'
