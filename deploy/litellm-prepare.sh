#!/bin/sh
set -eu

pod=huou07-litellm
volume=huou07-litellm-postgres

if ! podman pod exists "$pod"; then
  podman pod create --name "$pod" --network slirp4netns --publish 127.0.0.1:4000:4000
fi
if ! podman volume exists "$volume"; then
  podman volume create "$volume"
fi
