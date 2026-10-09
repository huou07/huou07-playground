#!/bin/sh
set -eu

attempt=0
while [ "$attempt" -lt 60 ]; do
  status=$(/usr/bin/curl --silent --output /dev/null --max-time 3 --write-out '%{http_code}' http://127.0.0.1:51821/ || true)
  case "$status" in
    2??|3??) exit 0 ;;
  esac
  attempt=$((attempt + 1))
  sleep 1
done
echo "wg-easy did not become ready on loopback port 51821." >&2
exit 1
