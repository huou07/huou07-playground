#!/bin/sh
set -eu

SERVICE=huou07-litellm
STATE_DIR=/var/lib/$SERVICE
RUNTIME_DIR=/run/$SERVICE
IMAGE=ghcr.io/berriai/litellm:v1.103.1
TEST_KEY=sk-local-test-master-key
EXPECTED=huou07-litellm-mock-route-ok

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this check with sudo so it can use the dedicated LiteLLM account." >&2
  exit 1
fi
if ! id "$SERVICE" >/dev/null 2>&1 || [ ! -d "$STATE_DIR" ] || [ ! -d "$RUNTIME_DIR" ]; then
  echo "The isolated LiteLLM service account is not installed." >&2
  exit 1
fi
for command in python3 systemctl systemd-run; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command is unavailable: $command" >&2
    exit 1
  fi
done
if [ "$(systemctl is-active "$SERVICE.service")" != active ]; then
  echo "The installed LiteLLM gateway must be active before this check." >&2
  exit 1
fi
if [ ! -x /usr/bin/podman ]; then
  echo "Podman is unavailable." >&2
  exit 1
fi

TMP_DIR=$(mktemp -d /run/huou07-litellm-mock.XXXXXX)
chmod 0750 "$TMP_DIR"
container_suffix=${TMP_DIR##*.}
CONTAINER=$SERVICE-mock-check-$container_suffix
UNIT=$CONTAINER.service
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
cleanup() {
  systemctl stop "$UNIT" >/dev/null 2>&1 || true
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
  case "$TMP_DIR" in
    /run/huou07-litellm-mock.*) rm -rf -- "$TMP_DIR" ;;
    *) echo "Refusing to remove unexpected temporary path: $TMP_DIR" >&2 ;;
  esac
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

cat > "$TMP_DIR/config.yaml" <<EOF
model_list:
  - model_name: huou07-mock
    litellm_params:
      model: openai/huou07-mock
      api_key: sk-placeholder-not-a-real-key
      api_base: http://127.0.0.1:1/v1
      mock_response: $EXPECTED
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
litellm_settings:
  telemetry: false
EOF

cat > "$TMP_DIR/run-check.sh" <<'INNER'
#!/bin/sh
set -eu
CONFIG=$1
PORT=$2
CONTAINER=$3
IMAGE=$4
TEST_KEY=$5
EXPECTED=$6
cleanup() {
  podman stop --time 10 "$CONTAINER" >/dev/null 2>&1 || podman rm --force "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

podman image exists "$IMAGE" || {
  echo "The pinned LiteLLM image is unavailable; this check will not pull an image." >&2
  exit 1
}
podman run --detach --rm \
  --name "$CONTAINER" \
  --network slirp4netns:allow_host_loopback=false \
  --publish "127.0.0.1:$PORT:4000" \
  --security-opt=no-new-privileges \
  --cap-drop=all \
  --volume "$CONFIG:/tmp/litellm-mock-check.yaml:ro" \
  --env "LITELLM_MASTER_KEY=$TEST_KEY" \
  --env LITELLM_TELEMETRY=False \
  "$IMAGE" --config /tmp/litellm-mock-check.yaml --host 0.0.0.0 --port 4000 --telemetry False >/dev/null

attempt=0
until curl --silent --fail --max-time 2 "http://127.0.0.1:$PORT/health/liveliness" >/dev/null; do
  if [ "$attempt" -ge 30 ]; then
    echo "The temporary LiteLLM proxy did not become healthy." >&2
    exit 1
  fi
  if ! podman container exists "$CONTAINER"; then
    echo "The temporary LiteLLM container exited before becoming healthy." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 1
done

unauthenticated_status=$(curl --silent --output /dev/null --max-time 5 --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --data '{"model":"huou07-mock","messages":[{"role":"user","content":"test"}]}' \
  "http://127.0.0.1:$PORT/v1/chat/completions")
if [ "$unauthenticated_status" != 401 ]; then
  echo "The temporary proxy returned HTTP $unauthenticated_status without authentication; expected 401." >&2
  exit 1
fi
echo "Unauthenticated request: rejected (401)"

response=$(curl --silent --show-error --fail --max-time 10 \
  --header "Authorization: Bearer $TEST_KEY" \
  --header 'Content-Type: application/json' \
  --data '{"model":"huou07-mock","messages":[{"role":"user","content":"test"}]}' \
  "http://127.0.0.1:$PORT/v1/chat/completions")
printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["choices"][0]["message"]["content"] == "huou07-litellm-mock-route-ok"'
echo "Authenticated mock completion: PASS"
INNER

chown -R "$SERVICE:$SERVICE" "$TMP_DIR"
chmod 0644 "$TMP_DIR/config.yaml"
chmod 0750 "$TMP_DIR/run-check.sh"

systemd-run --quiet --pipe --wait --collect --unit="$CONTAINER" \
  --uid="$SERVICE" --gid="$SERVICE" --working-directory="$STATE_DIR" \
  --setenv="HOME=$STATE_DIR" --setenv="XDG_RUNTIME_DIR=$RUNTIME_DIR" \
  --property=Delegate=yes --property=CPUQuota=100% --property=MemoryMax=1G \
  --property=TasksMax=256 --property=RuntimeMaxSec=120s --property=TimeoutStopSec=15s \
  /bin/sh "$TMP_DIR/run-check.sh" "$TMP_DIR/config.yaml" "$PORT" \
  "$CONTAINER-container" "$IMAGE" "$TEST_KEY" "$EXPECTED"
