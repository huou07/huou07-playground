#!/bin/sh
set -eu

attempt=0
while [ "$attempt" -lt 60 ]; do
  if /usr/bin/podman exec huou07-omniroute-redis redis-cli ping 2>/dev/null | grep -qx PONG; then
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
echo "OmniRoute Redis did not become ready." >&2
exit 1
