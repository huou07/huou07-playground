#!/bin/sh
set -eu

attempt=0
while [ "$attempt" -lt 60 ]; do
  if podman exec huou07-litellm-db pg_isready -U litellm >/dev/null 2>&1; then
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
echo "LiteLLM PostgreSQL did not become ready." >&2
exit 1
