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

## Memory architecture (two-tier)

### Global memory — `workspace/_memory/`
Cross-project knowledge: people, domain concepts, org context.
Point Obsidian vault at `workspace/` root to see the full graph including
cross-links between global and project memory.

| Directory | Contents |
|-----------|---------|
| `_memory/people/` | Stakeholders, team members, contacts |
| `_memory/concepts/` | Domain knowledge, frameworks, definitions |
| `_memory/inbox/` | Global unreviewed captures |

### Project memory — `workspace/projects/{slug}/_memory/`
Project-specific knowledge. Each project has its own wiki.

| Directory | Contents |
|-----------|---------|
| `stm/current.md` | Latest compact context summary (auto-written) |
| `inbox/` | Unreviewed orchestrator captures for this project |
| `decisions/` | Date-stamped decision records |
| `research/` | Research outputs and findings |
| `sessions/` | Completed agent session summaries |
| `INDEX.md` | Entry point — promote inbox items and add links here |

### Obsidian setup
- Vault root: `workspace/` (not `workspace/_memory/`)
- Wikilinks cross freely between global and project memory
- Do not change link format — `[[note-name]]` only
