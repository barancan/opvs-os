# opvs OS

Local-first, always-on PM operating system. Runs as a background daemon on macOS.
FastAPI backend · React/TypeScript/Vite frontend · SQLite · macOS launchd daemon.

---

## First-time setup

```sh
./scripts/setup.sh
./scripts/install-daemon.sh
```

Then open http://localhost:8000 and configure your API keys in **Settings → AI Models**.

## Development (hot reload, no daemon)

```sh
./scripts/dev.sh
```

- Backend: http://localhost:8000/api
- Frontend: http://localhost:5173 (Vite dev server, proxies `/api` and `/ws` to the backend)

## Daemon management

```sh
./scripts/install-daemon.sh    # install / reinstall as macOS LaunchAgent
./scripts/uninstall-daemon.sh  # remove — backend will no longer auto-start on login
```

## Logs

```sh
tail -f logs/backend.log        # stdout
tail -f logs/backend.error.log  # stderr
```

---

## How to use

### 1. Configure your AI provider

Open **Settings → AI Models** and add your API keys:

- **Anthropic** — required if you are using a `claude-*` model
- **Ollama** — enter the host (default `http://localhost:11434`) if you want to use a local model

Use **Test Connection** to verify each key.

### 2. Choose an orchestrator model

Open **Settings → Orchestrator** and set the **Model** field:

| Value | Routes to |
|---|---|
| `claude-sonnet-4-6` (default) | Anthropic API |
| `claude-opus-4-6`, `claude-haiku-4-5-20251001`, etc. | Anthropic API |
| `gemma3:4b`, `llama3.1:8b`, any other name | Ollama (local) |

If Ollama is unreachable when an Ollama model is configured, the orchestrator automatically falls back to `claude-sonnet-4-6` and creates a system notification.

### 3. Configure Ollama context window (optional)

For local models the context window is often smaller than Anthropic's 200k. Set **Ollama context window (tokens)** to match your model's limit (default: 8192). Context compaction triggers at 75% of this value.

### 4. Customise the system prompt (optional)

Click **Edit system prompt** in the Orchestrator section. There are two tabs:

- **Anthropic** — preamble used when the model starts with `claude-`
- **Ollama / Local** — preamble used for all other models

Leave a tab empty to use the built-in default. The dynamic context section (short-term memory, project context, kill switch state, pending notifications) is **always appended automatically** after your preamble.

### 5. Create a project

Go to **Projects** and click **New project**. Every project gets:
- A workspace directory at `workspace/projects/{slug}/`
- A `CONTEXT.md` file for per-project agent instructions
- A project-scoped short-term memory at `workspace/projects/{slug}/_memory/stm/current.md`

Use the **project switcher** in the sidebar to switch between projects. All chat history, notifications, and context compaction are scoped to the active project.

### 6. Manage skills

Skills extend the orchestrator with real-world capabilities. Go to **Projects**, open a project card, and scroll to the **Skills** section.

#### Available skills

| Skill | What it can do | Requires |
|---|---|---|
| **Workspace** | Read files, list directories, capture notes to `_memory/inbox/` | Nothing — always on |
| **Linear** | Read teams/projects/issues, create issues, update issues, post comments | Linear API key |

#### Enabling a skill

1. Ensure any required API key is configured in **Settings** first. Skills with an unconfigured key show an amber warning and their toggle is disabled.
2. Click the toggle next to the skill name to enable it. The toggle turns green immediately and the change persists.
3. To disable, click the toggle again.

The **Workspace** skill is always active and cannot be turned off — it gives the orchestrator read access to the project's workspace directory and the ability to capture notes.

#### Tool approval

When the orchestrator wants to execute a **write** action (creating an issue, posting a comment, etc.) it pauses and shows an **approval card** inline in the chat:

```
┌──────────────────────────────────────────────────┐
│ [Linear]  Create issue               ▼ details   │
│ Create issue "Investigate USDC..." in team ENG   │
│                                                  │
│  ✓ Approve       ✕ Reject                       │
└──────────────────────────────────────────────────┘
```

- Click **Approve** — the card transitions to *Executing…* and then shows the result once done.
- Click **Reject** — the card marks the action as *Rejected* and the orchestrator acknowledges in its response.
- Click the **▼** chevron to expand the raw parameters before deciding.

Read-only actions (listing issues, fetching a team, reading a file) execute silently without any approval prompt.

Approval cards clear automatically when the chat turn completes.

### 7. Chat with the orchestrator

Select a project and use the **Orchestrator** chat panel on the Dashboard. The panel shows live token usage (compacts automatically at 75% of the context window). Type `/compact` to clear history manually.

### 7. Notifications

The orchestrator creates notifications to surface information. The **Notification Inbox** on the Dashboard shows pending items. You can mark them complete or dismiss.

### 8. Kill switch

The kill switch halts all agent operations immediately. Activate it from **Settings → Danger Zone** or by asking the orchestrator directly.

To recover, enter a reason (10+ characters) and click **Recover System**. A recovery log is written to `workspace/_memory/inbox/`.

---

## Architecture

```
opvs-os/
├── backend/opvs/         FastAPI app, SQLAlchemy models, services, tests
├── frontend/src/          React 18 + TypeScript + Vite, Zustand, TanStack Query
├── workspace/             ICM file workspace — agents read/write here
├── scripts/               Setup, daemon, dev helpers
└── logs/                  Backend stdout/stderr (gitignored)
```

The backend runs as a macOS LaunchAgent (`com.opvs.backend`), starting on login and restarting on crash. In production the frontend is served by FastAPI from `frontend/dist/`. In development Vite runs on port 5173 and proxies API calls to the backend on port 8000.

### Orchestrator provider routing

- Model name starts with `claude-` → **Anthropic SDK** (streaming via `messages.stream`)
- Anything else → **Ollama** via HTTP streaming at `ollama_host/api/chat`

**Fallback:** if Ollama is unreachable, the orchestrator prepends a warning token, creates a system notification, and continues using `claude-sonnet-4-6`.

**Quota errors:** if Anthropic returns HTTP 429 or 529, operations halt entirely. A high-priority system notification is created. There is no silent fallback to another paid service.

### Context compaction

When cumulative token usage reaches 75% of the context window, the orchestrator summarises the conversation, writes it to the project's STM file, and trims history to the last 8 messages. The compact summary is injected at the start of every subsequent context load.

Context window sizes:
- Anthropic models: 200,000 tokens (compact threshold: 150,000)
- Ollama models: `ollama_context_window` setting (default 8,192; compact threshold: 75%)

### WebSocket events

| Event | Payload |
|---|---|
| `chat_token` | `{ token: string }` |
| `chat_complete` | `{ message_id: number, token_count: number }` |
| `chat_error` | `{ error: string }` |
| `compact_triggered` | `{ messages_compacted: number }` |
| `kill_switch_activated` | `{}` |
| `kill_switch_recovered` | `{}` |
| `notification_created` | notification object |
| `notification_updated` | notification object |
| `tool_approval_required` | `{ request_id, tool_name, platform, action, description, parameters }` |
| `tool_used` | `{ tool_name, platform }` |
| `tool_result` | `{ tool_name, success, content }` |
| `tool_rejected` | `{ request_id }` |

See `workspace/CLAUDE.md` for workspace conventions and agent rules.
