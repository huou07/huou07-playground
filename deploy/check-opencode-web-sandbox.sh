#!/bin/sh
set -eu

APP_USER=huou07-opencode
WORKSPACE_GROUP=huou07-opencode-workspaces
STATE_DIR=/var/lib/huou07-opencode
WORKSPACE_DIR=/srv/huou07-opencode-workspaces
DENIED=/etc/huou07-playground/.opencode-boundary-canary

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this check with sudo so it can test the installed service account." >&2
  exit 1
fi
if ! id "$APP_USER" >/dev/null 2>&1 || [ ! -d "$WORKSPACE_DIR" ] || [ ! -d "$STATE_DIR" ]; then
  echo "The isolated OpenCode web service is not installed." >&2
  exit 1
fi
owner=${SUDO_USER:-}
if [ -z "$owner" ] || [ "$owner" = root ]; then
  echo "Run this with sudo from the normal SSH owner's account." >&2
  exit 1
fi
owner_home=$(getent passwd "$owner" | cut -d: -f6)
canary=$(mktemp "$owner_home/.huou07-opencode-canary.XXXXXX")
workspace=$(runuser -u "$APP_USER" -- mktemp -d "$WORKSPACE_DIR/.boundary.XXXXXX")
state_probe="$STATE_DIR/.boundary-state-$$"
trap 'rm -f "$canary" "$DENIED" "$state_probe"; rm -rf "$workspace"' EXIT HUP INT TERM
printf 'owner-home-canary\n' > "$canary"
chmod 0644 "$canary"
rm -f "$DENIED"

systemd-run --quiet --wait --collect \
  --unit="huou07-opencode-boundary-$$" \
  --uid="$APP_USER" \
  --gid="$APP_USER" \
  --property="SupplementaryGroups=$WORKSPACE_GROUP" \
  --property=NoNewPrivileges=yes \
  --property=PrivateDevices=yes \
  --property=PrivateTmp=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property="ReadWritePaths=$STATE_DIR $WORKSPACE_DIR" \
  /bin/sh -ceu '
    workspace=$1
    canary=$2
    touch "$workspace/workspace-write"
    touch "$3"
    if cat "$canary" >/dev/null 2>&1; then
      echo "OpenCode sandbox can read the SSH owner home." >&2
      exit 21
    fi
    if touch "$4" 2>/dev/null; then
      echo "OpenCode sandbox can write outside its private state and workspace." >&2
      exit 22
    fi
  ' sh "$workspace" "$canary" "$state_probe" "$DENIED"

echo "OpenCode service boundary passed: workspace/state writes allowed; owner home hidden; /etc writes denied."
