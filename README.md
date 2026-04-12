# opvs OS

A local-first, always-on PM operating system. Runs as a macOS daemon with a FastAPI backend, React/TypeScript frontend, SQLite database, and an ICM-style file workspace.

## Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy (async), aiosqlite, Alembic, APScheduler, Anthropic SDK
- **Frontend**: Vite, React 18, TypeScript, Zustand, TanStack Query, Tailwind CSS, shadcn/ui
- **Database**: SQLite via aiosqlite, migrations via Alembic

## Setup

```sh
# Install Python dependencies
pip install pip-tools
pip-compile backend/requirements.in -o backend/requirements.txt --generate-hashes
pip-compile backend/requirements-dev.in -o backend/requirements-dev.txt --generate-hashes
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Run migrations
cd backend && alembic upgrade head && cd ..

# Start backend (from project root)
uvicorn opvs.main:app --host 127.0.0.1 --port 8000
```

## Development

```sh
# Type check
cd backend && mypy opvs/

# Lint
ruff check backend/opvs/

# Tests
pytest backend/opvs/tests/ -v
```

Secrets go in `.env.local` at the project root (gitignored).
