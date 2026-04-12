# READ-ONLY — do not modify this file

# opvs OS Workspace Root

This is the working directory for the opvs OS orchestrator and all agent instances.
Agents read context from this directory. Only the orchestrator may write here,
and only with user approval.

## Directory guide

| Directory | Purpose | Who writes |
|-----------|---------|------------|
| `_memory/stm/current.md` | Short-term memory: compact summary of recent context | Orchestrator only, after `/compact` |
| `_memory/inbox/` | Unreviewed orchestrator captures awaiting user promotion | Orchestrator only |
| `_memory/` (rest) | Long-term memory wiki — Obsidian-compatible `[[wikilinks]]` | User-promoted from inbox |
| `_agents/` | Persona definitions — one subdirectory per agent persona | User via Settings UI |
| `_jobs/` | Scheduled job definitions in JSON format | User via Jobs UI |
| `sessions/` | Per-agent-run isolated working directories | Agent runner (scoped to own session) |

## Rules enforced by the application

1. Agents may only read/write files inside their own `sessions/{session_id}/` directory.
2. Only the orchestrator may write to `_memory/`, and only with explicit user approval.
3. No agent may execute shell commands without user approval recorded in the session log.
4. Files with `# READ-ONLY` in their first line must never be modified by any agent.
5. Agents may not traverse `../` outside the workspace root.

## For Obsidian users

Point Obsidian at `workspace/_memory/` as a vault to view long-term memory as a graph.
All wiki links use standard `[[note-name]]` syntax. Do not change this format.
