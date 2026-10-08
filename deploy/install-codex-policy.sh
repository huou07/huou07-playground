#!/bin/sh
set -eu

SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
POLICY="$SOURCE/codex-requirements.toml"
TARGET=/etc/codex/requirements.toml

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root (for example: sudo ./deploy/install-codex-policy.sh)." >&2
  exit 1
fi
if [ ! -f "$POLICY" ]; then
  echo "Missing Codex policy file: $POLICY" >&2
  exit 1
fi
if [ -e "$TARGET" ]; then
  if cmp -s "$POLICY" "$TARGET"; then
    echo "The huou07 Codex policy is already installed."
    exit 0
  fi
  echo "$TARGET already exists with different contents; merge the policy manually." >&2
  exit 1
fi

install -d -o root -g root -m 0755 /etc/codex
install -o root -g root -m 0644 "$POLICY" "$TARGET"
echo "Installed the managed huou07 Codex workspace policy."
echo "Run ./deploy/check-codex-policy.sh as the Codex owner to verify it."
