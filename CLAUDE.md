# opvs OS — Project Guide for Claude Code

## What this is

A local-first, always-on PM operating system. FastAPI backend, React/TypeScript/Vite frontend,
SQLite database, macOS launchd daemon, ICM-style file workspace.

## Repository

https://github.com/barancan/opvs-os.git

## Git workflow

- Branch: always work on a feature branch, never commit directly to `main`
- Branch naming: `phase-1/backend-scaffold`, `phase-2/orchestrator`, etc.
- Commits: small, frequent, descriptive. Commit after each file or logical unit — not at the end of a whole prompt.
- Never commit: `.env.local`, `*.db`, `logs/`, `.venv/`, `frontend/node_modules/`, `frontend/dist/`
- After completing a prompt and passing all success criteria: commit, push, open a PR to main.

## First-time git setup (run once)

```sh
git init
git remote add origin https://github.com/barancan/opvs-os.git
git checkout -b phase-1/foundation
```

## Stack

- Backend: Python 3.11+, FastAPI, SQLAlchemy (async), aiosqlite, Alembic, APScheduler, Anthropic SDK
- Frontend: Vite, React 18, TypeScript (strict), Zustand, TanStack Query, Tailwind CSS, shadcn/ui
- Database: SQLite via aiosqlite, migrations via Alembic
- Dependency management: pip-tools (never edit requirements.txt manually)

## Non-negotiable rules

- All Python must pass strict mypy with zero errors
- All TypeScript must build with zero errors — no `any`, no `@ts-ignore`
- Async throughout — no sync DB calls
- No secrets in source code or committed files
- POSIX sh only in scripts — no bash-specific syntax
- Tests use in-memory SQLite — never touch the dev database
- We follow TDD. When planning make sure to generate tests.

## Project structure

- `backend/opvs/` — Python package
- `frontend/src/` — React app
- `workspace/` — ICM file workspace (agents read/write here within strict boundaries)
- `scripts/` — setup, daemon install/uninstall, dev mode
- `logs/` — backend stdout/stderr (gitignored)

## Build phases

Phase 1 (current): Foundation — backend scaffold, frontend scaffold, workspace + daemon scripts
Phase 2: Orchestrator + Dashboard
Phase 3: Agent system + personas
Phase 4: Jobs + Linear integration
Phase 5: Memory system + analytics

## Do not build beyond the current phase prompt without being asked.

## Known implementation decisions (do not change these)

### SQLAlchemy

- Use `DeclarativeBase` class (SQLAlchemy 2.0 style), not `declarative_base()` — required for strict mypy
- Example: `class Base(DeclarativeBase): pass`

### Alembic + asyncio

- Do not call `alembic.command.upgrade()` directly inside an async lifespan — causes nested event loop conflict
- Use `asyncio.to_thread()` to run Alembic migrations from the lifespan handler

### Alembic path resolution

- Set `script_location` and `sqlalchemy.url` programmatically in `main.py`, not via `alembic.ini`
- This ensures paths resolve correctly when uvicorn runs from the project root
