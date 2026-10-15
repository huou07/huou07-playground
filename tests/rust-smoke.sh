#!/bin/sh
set -eu

binary=${1:?Pass the built H07P Rust server binary}
port=18765
base=http://127.0.0.1:$port
log=$(mktemp)
STATIC_DIR="$PWD/web/static" HOST=127.0.0.1 PORT="$port" "$binary" >"$log" 2>&1 &
server_pid=$!
cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  rm -f "$log"
}
trap cleanup EXIT HUP INT TERM

ready=0
for attempt in $(seq 1 50); do
  if curl --silent --show-error --fail "$base/api/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    break
  fi
  sleep 0.1
done
if [ "$ready" -ne 1 ]; then
  cat "$log" >&2
  echo "Rust dashboard did not become ready." >&2
  exit 1
fi

health=$(curl --silent --show-error --fail -D - "$base/api/health")
printf '%s\n' "$health" | grep -Fq '{"ok":true}'
printf '%s\n' "$health" | grep -Eiq '^cache-control: no-store'
printf '%s\n' "$health" | grep -Eiq '^content-type: application/json; charset=utf-8'
html=$(curl --silent --show-error --fail -D "$log" "$base/")
printf '%s\n' "$html" | grep -Fq '<title>Home · huou07 playground</title>'
printf '%s\n' "$html" | grep -Fq 'data-view="settings"'
grep -Eiq '^content-security-policy: default-src' "$log"
grep -Eiq '^x-content-type-options: nosniff' "$log"
curl --silent --show-error --fail "$base/navigation.js" | grep -Fq 'function showRoute'
status=$(curl --silent --show-error --path-as-is -o /dev/null -w '%{http_code}' "$base/%2e%2e/app.py")
[ "$status" = 404 ]

if STATIC_DIR="$PWD/web/static" HOST=0.0.0.0 PORT=18766 "$binary" >"$log" 2>&1; then
  echo "Rust dashboard unexpectedly accepted a non-loopback listener." >&2
  exit 1
fi
grep -Fq 'Only loopback binding is supported' "$log"
