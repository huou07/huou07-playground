#!/bin/sh
set -eu

binary=${1:?Pass the built H07P Rust server binary}
port=18765
base=http://127.0.0.1:$port
fixture=$(mktemp -d)
chmod 700 "$fixture"
log="$fixture/server.log"
mkdir "$fixture/state"
# Populate only this disposable test database; production authentication is unchanged.
python3 - "$fixture" <<'PYFIXTURE'
import hashlib, pathlib, secrets, sqlite3, sys, time
root = pathlib.Path(sys.argv[1])
token, csrf = secrets.token_hex(32), secrets.token_hex(32)
with sqlite3.connect(root / 'state/owner.db') as db:
    db.execute('CREATE TABLE sessions(token TEXT PRIMARY KEY,username TEXT,csrf TEXT,expires INTEGER)')
    db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), 'synthetic-owner', csrf, int(time.time()) + 600))
(root / 'owner-header').write_text('Cookie: h07p_owner=' + token + '\n')
(root / 'owner-header').chmod(0o600)
(root / 'owner-proof-header').write_text((root / 'owner-header').read_text() + 'X-H07P-CSRF: ' + csrf + '\n')
(root / 'owner-proof-header').chmod(0o600)
PYFIXTURE
H07P_STATE_DIR="$fixture/state" APPS_FILE="$fixture/apps.json" STATIC_DIR="$PWD/web/static" HOST=127.0.0.1 PORT="$port" "$binary" >"$log" 2>&1 &
server_pid=$!
cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  rm -rf "$fixture"
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
printf '%s\n' "$health" | grep -Eiq '^content-type: application/json(; charset=utf-8)?'
html=$(curl --silent --show-error --fail -D "$log" "$base/")
printf '%s\n' "$html" | grep -Fq '<title>Home · huou07 playground</title>'
printf '%s\n' "$html" | grep -Fq 'data-view="settings"'
grep -Eiq '^content-security-policy: default-src' "$log"
grep -Eiq '^x-content-type-options: nosniff' "$log"
curl --silent --show-error --fail "$base/navigation.js" | grep -Fq 'function showRoute'
status=$(curl --silent --show-error --path-as-is -o /dev/null -w '%{http_code}' "$base/%2e%2e/app.py")
[ "$status" = 404 ]

status=$(curl --silent --show-error -o /dev/null -w '%{http_code}' "$base/api/metrics")
[ "$status" = 401 ]
status=$(curl --silent --show-error -H @"$fixture/owner-header" -o /dev/null -w '%{http_code}' "$base/api/metrics")
[ "$status" = 403 ]
curl --silent --show-error --fail -H @"$fixture/owner-header" "$base/api/owner/session" >"$fixture/cookie-session.json"
python3 - "$fixture/cookie-session.json" <<'PYSESSION'
import json, sys
session = json.load(open(sys.argv[1]))
assert session.get('authenticated') is False
assert 'csrf' not in session
PYSESSION
owner_get() {
  curl --silent --show-error --fail --max-time 15 -H @"$fixture/owner-proof-header" "$1"
}
for endpoint in metrics processes services cockpit files vpn private-service-ports apps; do
  owner_get "$base/api/$endpoint" >"$fixture/response.json"
  python3 - "$fixture/response.json" <<'PYJSON'
import json, sys
assert isinstance(json.load(open(sys.argv[1])), dict)
PYJSON
done
session=$(owner_get "$base/api/owner/session")
printf '%s\n' "$session" | grep -Fq '"authenticated":true'
status=$(curl --silent --show-error -H @"$fixture/owner-header" -H 'Content-Type: application/json' -d '{}' -o /dev/null -w '%{http_code}' "$base/api/apps")
[ "$status" = 403 ]

if H07P_STATE_DIR="$fixture/state" STATIC_DIR="$PWD/web/static" HOST=0.0.0.0 PORT=18766 "$binary" >"$log" 2>&1; then
  echo "Rust dashboard unexpectedly accepted a non-loopback listener." >&2
  exit 1
fi
grep -Eq 'Only loopback binding is supported|Server binds loopback' "$log"
