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
