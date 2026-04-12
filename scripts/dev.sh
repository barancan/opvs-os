#!/bin/sh
set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

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

# Wait for backend to start, then verify it is still running
sleep 1
if ! kill -0 $BACKEND_PID 2>/dev/null; then
  echo "ERROR: Backend failed to start. Last 10 lines of error log:" >&2
  tail -n 10 logs/backend.error.log >&2
  exit 1
fi

echo "Starting frontend on http://localhost:5173 ..."
cd frontend && npm run dev
