#!/bin/sh
set -eu

attempt=0
while [ "$attempt" -lt 300 ]; do
  if /usr/bin/curl --fail --silent --show-error --max-time 3 http://127.0.0.1:20128/healthz >/dev/null 2>&1; then
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
echo "OmniRoute did not become ready on loopback port 20128." >&2
exit 1
