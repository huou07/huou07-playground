#!/bin/sh
set -eu

IMAGE=docker.io/library/debian@sha256:918311b7b6c4c6f68b232ba516584925f6c78ad82b6fd534b98979df6438e483

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this check as the unprivileged Podman owner, not root." >&2
  exit 1
fi
if ! command -v podman >/dev/null 2>&1 || [ "$(podman info --format '{{.Host.Security.Rootless}}')" != true ]; then
  echo "Rootless Podman is unavailable for this user." >&2
  exit 1
fi

workspace=$(mktemp -d)
canary=$(mktemp "${HOME:?}/.huou07-sandbox-canary.XXXXXX")
trap 'rm -rf "$workspace"; rm -f "$canary"' EXIT HUP INT TERM
printf 'host-only-canary\n' >"$canary"

podman run --rm \
  --userns=keep-id \
  --user "$(id -u):$(id -g)" \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --read-only \
  --network=slirp4netns:allow_host_loopback=false \
  --pids-limit=128 \
  --memory=1g \
  --volume "$workspace:/workspace:rw" \
  --workdir=/workspace \
  "$IMAGE" sh -ceu '
    touch /workspace/allowed-write
    test -f /workspace/allowed-write
    if touch /outside-write 2>/dev/null; then
      echo "Sandbox allowed a write outside the workspace." >&2
      exit 21
    fi
    if test -r "$1"; then
      echo "Sandbox could read a host-home canary." >&2
      exit 22
    fi
    if test -S /run/podman/podman.sock || test -S /run/user/$(id -u)/podman/podman.sock; then
      echo "Sandbox can reach the host Podman socket." >&2
      exit 23
    fi
  ' sh "$canary"

echo "Rootless workspace boundary passed."
