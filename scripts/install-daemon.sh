#!/bin/sh
set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

echo "==> Installing opvs OS daemon"

# Check uvicorn is available in venv
if [ ! -f "$PROJECT_ROOT/.venv/bin/uvicorn" ]; then
  echo "ERROR: .venv/bin/uvicorn not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

# Check the template plist exists
if [ ! -f "$PROJECT_ROOT/com.opvs.backend.plist" ]; then
  echo "ERROR: com.opvs.backend.plist not found at project root." >&2
  exit 1
fi

DEST="$HOME/Library/LaunchAgents/com.opvs.backend.plist"

# Ensure LaunchAgents directory exists
mkdir -p "$HOME/Library/LaunchAgents"

# Unload existing service if installed (ignore errors — it may not be loaded)
if [ -f "$DEST" ]; then
  echo "Unloading existing daemon..."
  launchctl unload "$DEST" 2>/dev/null || true
fi

# Replace placeholder and write to LaunchAgents
echo "Installing plist to $DEST"
sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  "$PROJECT_ROOT/com.opvs.backend.plist" \
  > "$DEST"

# Ensure logs directory exists before loading
mkdir -p "$PROJECT_ROOT/logs"

# Load the service
launchctl load "$DEST"

# Wait for it to start
sleep 3

# Check status
if launchctl list com.opvs.backend 2>/dev/null | grep -q '"com.opvs.backend"'; then
  echo "Daemon installed and running."
  echo "Backend logs:   $PROJECT_ROOT/logs/backend.log"
  echo "Backend errors: $PROJECT_ROOT/logs/backend.error.log"
else
  echo "Daemon installed but may not be running yet."
  echo "Check logs: $PROJECT_ROOT/logs/backend.error.log"
fi

echo ""
echo "opvs OS will now start automatically when you log in."
