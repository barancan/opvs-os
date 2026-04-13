#!/bin/sh
set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

# Kill any leftover backend process listening on port 8000.
# Use -sTCP:LISTEN to target only the listener, not browsers or other clients
# that have open connections to the port.
OLD_PID=$(lsof -ti:8000 -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
  echo "Killing leftover process on port 8000 (PID $OLD_PID) and its children..."
  # Kill child processes first, then the parent
  pkill -P "$OLD_PID" 2>/dev/null || true
  kill "$OLD_PID" 2>/dev/null || true
  # Wait until the port is actually free (up to 5s) before proceeding
  i=0
  while [ $i -lt 5 ]; do
    if ! lsof -ti:8000 -sTCP:LISTEN > /dev/null 2>&1; then
      break
    fi
    sleep 1
    i=$((i + 1))
  done
fi

# Check venv exists
if [ ! -d ".venv" ]; then
  echo "ERROR: .venv not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

# Activate
. .venv/bin/activate

# Ensure logs directory exists
mkdir -p logs

echo "Starting backend on http://localhost:8000 ..."

PYTHONPATH="$PROJECT_ROOT/backend" uvicorn opvs.main:app \
  --reload --host 127.0.0.1 --port 8000 \
  > logs/backend.log 2> logs/backend.error.log &
BACKEND_PID=$!
echo "$BACKEND_PID" > .dev-backend.pid

# Trap to clean up backend on exit
trap 'kill $BACKEND_PID 2>/dev/null; rm -f .dev-backend.pid; echo "Backend stopped."' EXIT INT TERM

# Poll /api/health until the backend is actually accepting requests.
# kill -0 only proves the supervisor process is alive; the worker child
# (which runs migrations and binds port 8000) takes longer.
echo "Waiting for backend to be ready..."
READY=0
i=0
while [ $i -lt 30 ]; do
  if curl -sf "http://127.0.0.1:8000/api/health" > /dev/null 2>&1; then
    READY=1
    break
  fi
  if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "ERROR: Backend process died. Last 10 lines of error log:" >&2
    tail -n 10 logs/backend.error.log >&2
    exit 1
  fi
  sleep 1
  i=$((i + 1))
done
if [ $READY -eq 0 ]; then
  echo "ERROR: Backend did not become ready within 30 seconds." >&2
  tail -n 10 logs/backend.error.log >&2
  exit 1
fi
echo "Backend ready."

echo "Starting frontend on http://localhost:5173 ..."
cd frontend && npm run dev
