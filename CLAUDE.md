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

Phase 1: Foundation — backend scaffold, frontend scaffold, workspace + daemon scripts ✓ COMPLETE
Phase 2: Orchestrator + Dashboard ✓ COMPLETE
Phase 2.5: Projects (backend + frontend) ✓ COMPLETE
Phase 2.5+: Ollama provider support + editable system prompts ✓ COMPLETE (branch: phase-3/ollama-orchestrator-support)
Phase 3 (next): Agent system + personas
Phase 4: Jobs + Linear integration
Phase 5: Memory system + analytics

## Do not build beyond the current phase prompt without being asked.

## Known implementation decisions (do not change these)

### Settings service — test_connection

- Must accept `db: AsyncSession` and read API keys from the database, not from the
  pydantic Settings singleton — the singleton reads from environment variables which
  are empty until restart; saved keys live in SQLite
- Always cast retrieved DB values with explicit `str()` before use in HTTP headers
  to prevent bytes-vs-string bugs

### Connection status persistence

- Connection test results (ok/error/untested per service) live in Zustand, not in
  local component state — they must survive navigation away from Settings

### Node / Vite

- Vite is pinned to v5 (`vite@5`) — Vite 8 requires Node 20.19+ which may not be present
- `setup.sh` must check for Node >= 18, not just any Node version
- `@tailwindcss/vite` supports Vite 5 — do not upgrade Vite without testing

### shadcn/ui

- `toast` component removed from shadcn v4 — use `sonner` instead
- shadcn v4 uses `@theme inline` block for CSS variable mapping

### TypeScript 6

- `erasableSyntaxOnly` forbids parameter properties in constructors
- Assign class properties explicitly in the constructor body instead
- `baseUrl` is deprecated — use only `paths` in `tsconfig.app.json`

### SQLAlchemy

- Use `DeclarativeBase` class (SQLAlchemy 2.0 style), not `declarative_base()` — required for strict mypy
- Example: `class Base(DeclarativeBase): pass`

### Alembic + asyncio

- Do not call `alembic.command.upgrade()` directly inside an async lifespan — causes nested event loop conflict
- Use `asyncio.to_thread()` to run Alembic migrations from the lifespan handler

### Alembic path resolution

- Set `script_location` and `sqlalchemy.url` programmatically in `main.py`, not via `alembic.ini`
- This ensures paths resolve correctly when uvicorn runs from the project root

### API client URL strategy

- `client.ts` BASE_URL must be `''` (empty string) — always use relative URLs
- Vite proxy handles `/api` and `/ws` in dev mode
- FastAPI serves both API and static files in production — relative URLs hit the
  right server automatically
- Never hardcode `http://localhost:PORT` in frontend source code

### Linear API authentication

- Linear personal API keys (`lin_api_...`) use direct key auth — no `Bearer` prefix
- Header: `Authorization: {api_key}` not `Authorization: Bearer {api_key}`
- Bearer prefix is for OAuth tokens only

### 404 handling for settings

- `GET /api/settings/{key}` returns 404 if key not yet saved — this is expected
- Use `getSettingOrNull()` helper which returns null on 404, throws on other errors
- Treat null as "not yet configured", not as an error state

### Orchestrator constraints (enforced in code, documented here)

- orchestrator_service.py must never import subprocess, os.system, or os.popen
- Orchestrator only writes to workspace/\_memory/ — all other workspace writes
  require user approval
- Kill switch state stored in settings table as kill_switch_active / kill_switch_activated_at
- Context compaction triggers at 75% of context window:
  - Anthropic: 200k tokens → threshold 150k
  - Ollama: reads `ollama_context_window` setting (default 8192) → threshold 75%
- After compaction: keep last 8 messages + compact summary in DB
- Compact summary written to workspace/projects/{slug}/\_memory/stm/current.md (project-scoped)

### Notification ordering

- notifications ordered: orchestrator_prioritised DESC, priority DESC, created_at DESC
- agent_id / session_id / job_id are nullable strings — FK constraints added in Phase 3

### StrEnum for string enums

- Use `StrEnum` (Python 3.11 stdlib) instead of `str, Enum` — ruff UP042 rule enforces this
- Example: `class NotificationStatus(StrEnum): PENDING = "pending"`

### Orchestrator context loading

- Most recent `is_compact_summary=True` message is injected as a user message followed by
  an assistant ack: `"Understood. I have the context summary."` — keeps alternating role order
- All subsequent non-summary messages append after it
- Anthropic streaming: call `await stream.get_final_message()` inside the `async with` block

### Frontend — WS handlers location

- `useWebSocket` handlers that call `queryClient.invalidateQueries()` must live inside `AppInner`
  (which is inside `QueryClientProvider`), not in the outer `App` component
- Access queryClient via `useQueryClient()` hook

### Frontend — Dashboard layout chain

- AppShell `<main>`: `flex-1 h-full overflow-hidden`
- Dashboard root: `flex flex-col h-full overflow-hidden`
- This is required so the fixed-height OrchestratorChat stays pinned at the bottom
  without the outer page scrolling

### Dev tools not in requirements.in

- mypy, ruff, pytest, pytest-asyncio are not tracked in `requirements.in`
- Install manually into the venv: `.venv/bin/pip install mypy ruff pytest pytest-asyncio`

### Orchestrator provider routing

- Model name starting with "claude-" → Anthropic SDK
- Anything else → Ollama via /api/chat HTTP endpoint
- Detection: \_detect_provider(model: str) -> Literal["anthropic", "ollama"]

### Fallback chain

- Ollama unreachable → warn in chat with prefix, create system notification,
  fall back to claude-sonnet-4-6 (ORCHESTRATOR_MODEL_DEFAULT)
- Anthropic quota/rate limit (HTTP 429, 529, RateLimitError) → halt entirely,
  create high-priority system notification, broadcast WS_CHAT_ERROR
  DO NOT fall back to another paid service

### Editable preambles

- orchestrator_preamble_anthropic — custom static prompt for Anthropic models
- orchestrator_preamble_ollama — custom static prompt for Ollama models
- Empty string = use hardcoded default (ANTHROPIC_PREAMBLE_DEFAULT / OLLAMA_PREAMBLE_DEFAULT)
- Dynamic state (STM, project context, kill switch, notifications) always appends after

### Context window

- Anthropic: 200_000 tokens, compact at 75% = 150_000
- Ollama: read ollama_context_window setting (default 8192), compact at 75%
- Token counts from Ollama: prompt_eval_count (input) + eval_count (output)

### Skills architecture

- Skills live in backend/opvs/skills/ — one file per platform
- WorkspaceSkill is always enabled (no DB row needed)
- All other skills: enabled in project_skills table AND require API key configured
- Read tools: requires_approval=False — execute silently, emit WS_TOOL_USED
- Write tools: requires_approval=True — emit WS_TOOL_APPROVAL_REQUIRED, await asyncio.Event
- Approval waits indefinitely — no timeout
- Path traversal prevention: WorkspaceSkill.\_resolve_safe() returns None for ../

### Agentic loop

- Max 10 iterations (MAX_LOOP_ITERATIONS = 10)
- Tool exchange messages NOT persisted to DB — only final text response saved
- Stop conditions: stop_reason == "end_turn" OR no tool_results in current iteration
- Approval state: module-level \_pending_approvals dict + \_approval_decisions dict
- resolve_approval() called by approve/reject endpoints — sets asyncio.Event

### Linear API

- Authentication: direct key, no Bearer prefix
- All queries via POST https://api.linear.app/graphql
- Read tools: teams, projects, issues (with filters), get_issue, search_issues
- Write tools: create_issue, update_issue, create_comment (all require approval)

### Ollama tool use

- Uses /v1/chat/completions endpoint (OpenAI-compatible) for tool support
- /api/chat does not reliably support tool_calls across all models
- Tool format converted from Anthropic schema to OpenAI function format

### Agent system

- Personas are global (not project-scoped) — reusable across projects
- Sessions are project-scoped — each run tied to a project
- Persona config is snapshot at spawn time — editing persona doesn't affect running sessions
- Concurrency limit: settings key agent_max_concurrent (default 2)
- Halt: sets asyncio.Event per session_uuid — stops loop at next iteration check
- Chatroom: agent_messages table, project-scoped, fully public
- Agent questions: detected by text ending in "?" → posts to chatroom, awaits response event
- Write tool approval for agents: goes through chatroom (not the orchestrator approval card)
- WS client*id for agents: f"agent*{session_uuid}"
- AgentSession.enabled_skills_snapshot: comma-separated string, same format as Persona.enabled_skills

### Agent memory on completion

- Session output → workspace/projects/{slug}/_memory/inbox/session_{ts}\_{uuid8}.md
- Activity log → workspace/projects/{slug}/\_memory/activity_log.md (max 50 entries)
- Orchestrator loads activity_log.md in system prompt under "Recent agent activity"
- STM is NOT directly written by agents — inbox + activity log feed into compaction

### Offline @ mention

- Mention detection in post_user_reply checks active sessions first
- Active session found → deliver_mention() (inject into next loop iteration)
- No active session → reply_offline_mention() (single-turn, no tools, no loop)
- Offline reply uses persona's configured model and reads project STM + activity log
- Offline sender name: "{persona.name} (offline)"
