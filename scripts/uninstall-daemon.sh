#!/bin/sh
set -eu

DEST="$HOME/Library/LaunchAgents/com.opvs.backend.plist"

if [ ! -f "$DEST" ]; then
  echo "Daemon is not installed."
  exit 0
fi

echo "==> Uninstalling opvs OS daemon"

launchctl unload "$DEST" 2>/dev/null || true
rm "$DEST"

echo "Daemon removed. The backend will no longer start automatically."
echo "The backend may still be running in this session. Kill it with: lsof -ti:8000 | xargs kill"
