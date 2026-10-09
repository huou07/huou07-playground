#!/bin/sh
set -eu

pod=huou07-omniroute
if ! podman pod exists "$pod"; then
  podman pod create --name "$pod" --network slirp4netns \
    --publish 127.0.0.1:20128:20128 \
    --publish 127.0.0.1:20129:20129 \
    --publish 127.0.0.1:20132:20132
fi
