#!/bin/sh
set -eu

network=huou07-litellm
volume=huou07-litellm-postgres

if ! podman network exists "$network"; then
  podman network create "$network"
fi
if ! podman volume exists "$volume"; then
  podman volume create "$volume"
fi
