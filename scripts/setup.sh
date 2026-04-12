#!/bin/sh
set -eu

# Move to project root (parent of this script's directory)
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

echo "==> opvs OS setup"

# 1. Check Python 3.11+
# Prefer a versioned binary if the default python3 is too old
PYTHON3=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" > /dev/null 2>&1; then
    _ver=$("$candidate" --version 2>&1 | sed 's/Python //')
    _major=$(echo "$_ver" | cut -d. -f1)
    _minor=$(echo "$_ver" | cut -d. -f2)
    if [ "$_major" -gt 3 ] || { [ "$_major" -eq 3 ] && [ "$_minor" -ge 11 ]; }; then
      PYTHON3="$candidate"
      PY_VERSION="$_ver"
      break
    fi
  fi
done

if [ -z "$PYTHON3" ]; then
  echo "ERROR: Python 3.11+ required but not found. Install from https://www.python.org/" >&2
  exit 1
fi
echo "Python $PY_VERSION ($PYTHON3) — OK"

# 2. Create virtual environment
if [ -d ".venv" ]; then
  echo "Virtual environment already exists, skipping creation."
else
  echo "==> Creating virtual environment"
  "$PYTHON3" -m venv .venv
fi

# 3. Activate
. .venv/bin/activate

# 4. Upgrade pip
echo "==> Upgrading pip"
pip install --quiet --upgrade pip

# 5. Install pip-tools
echo "==> Installing pip-tools"
pip install --quiet pip-tools

# 6. Compile requirements (only if stale or missing)
if [ ! -f backend/requirements.txt ] || [ backend/requirements.in -nt backend/requirements.txt ]; then
  echo "==> Compiling backend/requirements.txt"
  pip-compile backend/requirements.in -o backend/requirements.txt --quiet
else
  echo "backend/requirements.txt is up to date, skipping compile."
fi

if [ ! -f backend/requirements-dev.txt ] || [ backend/requirements-dev.in -nt backend/requirements-dev.txt ]; then
  echo "==> Compiling backend/requirements-dev.txt"
  pip-compile backend/requirements-dev.in -o backend/requirements-dev.txt --quiet
else
  echo "backend/requirements-dev.txt is up to date, skipping compile."
fi

# 7. Install requirements
echo "==> Installing backend dependencies"
pip install --quiet -r backend/requirements.txt

# 8. Run database migrations
echo "==> Running database migrations"
cd backend && alembic upgrade head && cd "$PROJECT_ROOT"

# 9. Create logs directory
mkdir -p logs

# 10. Install frontend dependencies
echo "==> Installing frontend dependencies"
cd frontend && npm install --silent && cd "$PROJECT_ROOT"

# 11. Build frontend
echo "==> Building frontend"
cd frontend && npm run build && cd "$PROJECT_ROOT"

# 12. Create .env.local if missing
if [ ! -f .env.local ]; then
  cp .env.local.example .env.local
  echo ""
  echo "Created .env.local from example — add your API keys before starting."
fi

echo ""
echo "==> Setup complete!"
echo ""
echo "Next steps:"
echo "  Development (hot reload):  ./scripts/dev.sh"
echo "  Install daemon (auto-start): ./scripts/install-daemon.sh"
echo "  Open frontend:             http://localhost:5173"
