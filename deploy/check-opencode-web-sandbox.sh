#!/bin/sh
set -eu

APP_USER=huou07-opencode
WORKSPACE_GROUP=huou07-opencode-workspaces
STATE_DIR=/var/lib/huou07-opencode
WORKSPACE_DIR=/srv/huou07-opencode-workspaces
SANDBOX=/usr/local/libexec/huou07-opencode/bash
BINARY=/usr/local/libexec/huou07-opencode/opencode
CONFIG=/var/lib/huou07-opencode/config/opencode/opencode.json
DENIED=/etc/huou07-playground/.opencode-boundary-canary

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this check with sudo so it can test the installed service account." >&2
  exit 1
fi
if ! id "$APP_USER" >/dev/null 2>&1 || [ ! -d "$WORKSPACE_DIR" ] || [ ! -d "$STATE_DIR" ] || [ ! -x "$SANDBOX" ] || [ ! -x "$BINARY" ] || [ ! -f "$CONFIG" ]; then
  echo "The isolated OpenCode web sandbox is not installed." >&2
  exit 1
fi
owner=${SUDO_USER:-}
if [ -z "$owner" ] || [ "$owner" = root ]; then
  echo "Run this with sudo from the normal SSH owner's account." >&2
  exit 1
fi
owner_home=$(getent passwd "$owner" | cut -d: -f6)
canary=$(mktemp "$owner_home/.huou07-opencode-canary.XXXXXX")
project=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-project.XXXXXX")
sibling=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary-sibling.XXXXXX")
state_probe=$(mktemp "$STATE_DIR/.boundary-state.XXXXXX")
DENIED=$(mktemp /etc/huou07-playground/.opencode-boundary-canary.XXXXXX)
rm -f "$DENIED"
test_home=$(mktemp -d /tmp/huou07-opencode-config.XXXXXX)
chown "$APP_USER:$APP_USER" "$state_probe"
chmod 0600 "$state_probe"
chown "$APP_USER:$APP_USER" "$test_home"
trap 'rm -f "$canary" "$DENIED" "$state_probe"; rm -rf "$project" "$sibling" "$test_home"' EXIT HUP INT TERM
printf 'owner-home-canary\n' > "$canary"
chmod 0644 "$canary"
runuser -u "$APP_USER" -- sh -c 'printf sibling-canary > "$1/secret"' sh "$sibling"
runuser -u "$APP_USER" -- sh -c 'printf state-canary > "$1"' sh "$state_probe"
install -d -o "$APP_USER" -g "$APP_USER" -m 0700 "$test_home/config/opencode" "$test_home/data" "$test_home/state" "$test_home/cache"
install -o "$APP_USER" -g "$APP_USER" -m 0600 "$CONFIG" "$test_home/config/opencode/opencode.json"

systemd-run --quiet --wait --collect \
  --unit="huou07-opencode-boundary-$$" \
  --uid="$APP_USER" \
  --gid="$APP_USER" \
  --setenv=OPENCODE_SERVER_PASSWORD=disposable-canary \
  --property="SupplementaryGroups=$WORKSPACE_GROUP" \
  --property="WorkingDirectory=$project" \
  --property=NoNewPrivileges=yes \
  --property=PrivateDevices=yes \
  --property=PrivateTmp=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property="ReadWritePaths=$STATE_DIR $WORKSPACE_DIR" \
  "$SANDBOX" -l -c '
    shopt -s expand_aliases
    [[ -f ~/.bashrc ]] && source ~/.bashrc >/dev/null 2>&1 || true
    cd -- "$1"
    test -z "${OPENCODE_SERVER_PASSWORD-}"
    test ! -r "$2"
    test ! -r "$3"
    test ! -e "$4/secret"
    printf workspace-ok > workspace-write
    test "$(cat workspace-write)" = workspace-ok
    if touch "$5" 2>/dev/null; then
      echo "OpenCode shell can write outside its private state and workspace." >&2
      exit 22
    fi
  ' opencode "$project" "$canary" "$state_probe" "$sibling" "$DENIED"

config_output=$(runuser -u "$APP_USER" -- env HOME="$test_home" XDG_CONFIG_HOME="$test_home/config" XDG_DATA_HOME="$test_home/data" XDG_STATE_HOME="$test_home/state" XDG_CACHE_HOME="$test_home/cache" NO_COLOR=1 "$BINARY" debug config)
printf '%s' "$config_output" | python3 -c '
import json,sys
config=json.load(sys.stdin)
permissions=config.get("permission", {})
external=permissions.get("external_directory", {})
assert config.get("shell") == "/usr/local/libexec/huou07-opencode/bash"
assert external.get("/var/lib/huou07-opencode") == "deny"
assert external.get("/var/lib/huou07-opencode/**") == "deny"
'

echo "OpenCode sandbox passed: owner home, service state, sibling workspaces, and server environment are hidden; the selected workspace is writable."
