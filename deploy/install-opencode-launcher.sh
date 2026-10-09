#!/bin/sh
set -eu

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this launcher setup as the OpenCode owner's normal account." >&2
  exit 1
fi

BIN_DIR="$HOME/.opencode/bin"
BINARY="$BIN_DIR/opencode"
REAL_BINARY="$BIN_DIR/opencode.real"
WRAPPER="$BIN_DIR/.opencode-wrapper.$$"

if [ -f "$BINARY" ] && ! grep -aFq 'huou07 OpenCode launcher v1' "$BINARY"; then
  if [ -x "$REAL_BINARY" ]; then
    install -m 0755 "$BINARY" "$REAL_BINARY.new"
    mv -f "$REAL_BINARY.new" "$REAL_BINARY"
  else
    mv "$BINARY" "$REAL_BINARY"
  fi
fi
if [ ! -x "$REAL_BINARY" ]; then
  echo "Install OpenCode first using its official Linux installer." >&2
  exit 1
fi

cat > "$WRAPPER" <<'EOF'
#!/bin/sh
# huou07 OpenCode launcher v1
set -eu
OPENCODE_DATA_HOME="$HOME/.opencode"
export XDG_CONFIG_HOME="$OPENCODE_DATA_HOME/config"
export XDG_DATA_HOME="$OPENCODE_DATA_HOME/data"
export XDG_STATE_HOME="$OPENCODE_DATA_HOME/state"
export XDG_CACHE_HOME="$OPENCODE_DATA_HOME/cache"
exec "$OPENCODE_DATA_HOME/bin/opencode.real" "$@"
EOF
chmod 0755 "$WRAPPER"
mv -f "$WRAPPER" "$BINARY"
echo "OpenCode now keeps its configuration, auth, sessions, and state under ~/.opencode."
