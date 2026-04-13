import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createPersona,
  deletePersona,
  listPersonas,
  updatePersona,
} from '@/api/personas'
import { haltSession, listSessions, spawnSession } from '@/api/sessions'
import { useAppStore } from '@/stores/useAppStore'
import type { Persona, PersonaCreate, PersonaUpdate, SessionStatus } from '@/types/api'
import { ApiError } from '@/api/client'

// ── Helpers ───────────────────────────────────────────────────────────────────

const AVAILABLE_SKILLS = [
  { id: 'workspace', label: 'Workspace', alwaysOn: true },
  { id: 'linear', label: 'Linear', alwaysOn: false },
]

const STATUS_COLORS: Record<SessionStatus, string> = {
  queued: 'text-zinc-400',
  running: 'text-green-400',
  waiting: 'text-amber-400',
  completed: 'text-zinc-600',
  failed: 'text-red-400',
  halted: 'text-zinc-600',
}

function StatusBadge({ status }: { status: SessionStatus }) {
  return (
    <span className={`text-xs font-medium ${STATUS_COLORS[status]}`}>{status}</span>
  )
}

function useElapsed(startedAt: string | null, active: boolean): string {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!active || !startedAt) return
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [active, startedAt])

  if (!startedAt) return ''
  const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}m ${s}s`
}

// ── Persona form ──────────────────────────────────────────────────────────────

const DEFAULT_FORM: PersonaCreate = {
  name: '',
  description: '',
  model: 'claude-sonnet-4-6',
  instructions: '',
  enabled_skills: ['workspace'],
  temperature: 0.7,
  max_tokens: 4096,
}

interface PersonaFormProps {
  initial?: Persona
  onSave: (data: PersonaCreate | PersonaUpdate) => void
  onCancel: () => void
  saving: boolean
}

function PersonaForm({ initial, onSave, onCancel, saving }: PersonaFormProps) {
  const [form, setForm] = useState<PersonaCreate>(
    initial
      ? {
          name: initial.name,
          description: initial.description ?? '',
          model: initial.model,
          instructions: initial.instructions,
          enabled_skills: initial.enabled_skills,
          temperature: initial.temperature,
          max_tokens: initial.max_tokens,
        }
      : { ...DEFAULT_FORM },
  )

  function toggleSkill(id: string) {
    setForm((f) => ({
      ...f,
      enabled_skills: f.enabled_skills?.includes(id)
        ? f.enabled_skills.filter((s) => s !== id)
        : [...(f.enabled_skills ?? []), id],
    }))
  }

  return (
    <div className="space-y-3 p-4 bg-zinc-900 rounded-lg border border-zinc-700">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Name *</label>
          <input
            className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5
                       text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Researcher"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Model</label>
          <input
            className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5
                       text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
            value={form.model ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            placeholder="claude-sonnet-4-6 or gemma3:4b"
          />
          <p className="text-xs text-zinc-600 mt-0.5">Use Ollama model names like gemma3:4b</p>
        </div>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-1">Description</label>
        <input
          className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5
                     text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          value={form.description ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          placeholder="Optional description"
        />
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-1">Instructions</label>
        <textarea
          rows={4}
          className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5
                     text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-y"
          value={form.instructions ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, instructions: e.target.value }))}
          placeholder="Describe this persona's role and behavior…"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">
            Temperature: {form.temperature?.toFixed(1)}
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={form.temperature ?? 0.7}
            onChange={(e) => setForm((f) => ({ ...f, temperature: parseFloat(e.target.value) }))}
            className="w-full accent-zinc-400"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Max Tokens</label>
          <input
            type="number"
            min={256}
            max={32768}
            className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5
                       text-zinc-200 focus:outline-none focus:border-zinc-500"
            value={form.max_tokens ?? 4096}
            onChange={(e) => setForm((f) => ({ ...f, max_tokens: parseInt(e.target.value, 10) }))}
          />
        </div>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-1">Skills</label>
        <div className="flex gap-3">
          {AVAILABLE_SKILLS.map((skill) => (
            <label key={skill.id} className="flex items-center gap-1.5 text-xs text-zinc-300">
              <input
                type="checkbox"
                checked={form.enabled_skills?.includes(skill.id) ?? false}
                disabled={skill.alwaysOn}
                onChange={() => !skill.alwaysOn && toggleSkill(skill.id)}
                className="accent-zinc-400"
              />
              {skill.label}
              {skill.alwaysOn && <span className="text-zinc-600">(always on)</span>}
            </label>
          ))}
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onSave(form)}
          disabled={saving || !form.name.trim()}
          className="text-sm px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : initial ? 'Save Changes' : 'Create Persona'}
        </button>
        <button
          onClick={onCancel}
          className="text-sm px-3 py-1.5 text-zinc-400 hover:text-zinc-200 rounded"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Spawn panel ───────────────────────────────────────────────────────────────

interface SpawnPanelProps {
  persona: Persona
  activeProjectId: number | null
  onClose: () => void
}

function SpawnPanel({ persona, activeProjectId, onClose }: SpawnPanelProps) {
  const [task, setTask] = useState('')
  const [spawning, setSpawning] = useState(false)
  const qc = useQueryClient()

  async function handleSpawn() {
    if (!task.trim() || activeProjectId === null || spawning) return
    setSpawning(true)
    try {
      await spawnSession(activeProjectId, persona.id, task.trim())
      toast.success(`Agent spawned: ${persona.name}`)
      void qc.invalidateQueries({ queryKey: ['sessions'] })
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error('Concurrency limit reached — wait for a running agent to finish')
      } else {
        toast.error('Failed to spawn agent')
      }
    } finally {
      setSpawning(false)
    }
  }

  return (
    <div className="mt-3 p-4 bg-zinc-900 rounded-lg border border-zinc-700">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-zinc-200">
          Spawn <span className="text-blue-400">{persona.name}</span>
        </span>
        <button onClick={onClose} className="text-xs text-zinc-500 hover:text-zinc-300">
          ✕
        </button>
      </div>

      {activeProjectId === null && (
        <p className="text-xs text-amber-400 mb-2">Select a project first.</p>
      )}

      <textarea
        rows={4}
        className="w-full text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5
                   text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-y"
        placeholder="Describe the task for this agent…"
        value={task}
        onChange={(e) => setTask(e.target.value)}
      />

      <div className="flex gap-2 mt-2">
        <button
          onClick={() => void handleSpawn()}
          disabled={!task.trim() || activeProjectId === null || spawning}
          className="text-sm px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {spawning ? 'Spawning…' : 'Spawn Agent'}
        </button>
        <button
          onClick={onClose}
          className="text-sm px-3 py-1.5 text-zinc-400 hover:text-zinc-200 rounded"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── PersonaCard ───────────────────────────────────────────────────────────────

interface PersonaCardProps {
  persona: Persona
  activeProjectId: number | null
  onEdited: () => void
}

function PersonaCard({ persona, activeProjectId, onEdited }: PersonaCardProps) {
  const [editing, setEditing] = useState(false)
  const [spawning, setSpawning] = useState(false)
  const qc = useQueryClient()

  const updateMutation = useMutation({
    mutationFn: (data: PersonaUpdate) => updatePersona(persona.id, data),
    onSuccess: () => {
      toast.success('Persona updated')
      setEditing(false)
      onEdited()
      void qc.invalidateQueries({ queryKey: ['personas'] })
    },
    onError: () => toast.error('Failed to update persona'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deletePersona(persona.id),
    onSuccess: () => {
      toast.success('Persona deleted')
      void qc.invalidateQueries({ queryKey: ['personas'] })
    },
    onError: () => toast.error('Failed to delete persona'),
  })

  return (
    <div className="border border-zinc-800 rounded-lg p-4 bg-zinc-900/50">
      {editing ? (
        <PersonaForm
          initial={persona}
          onSave={(data) => updateMutation.mutate(data as PersonaUpdate)}
          onCancel={() => setEditing(false)}
          saving={updateMutation.isPending}
        />
      ) : (
        <>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="text-sm font-medium text-zinc-200 truncate">{persona.name}</h3>
              {persona.description && (
                <p className="text-xs text-zinc-500 mt-0.5 line-clamp-1">{persona.description}</p>
              )}
            </div>
            <div className="flex gap-1.5 flex-shrink-0">
              <button
                onClick={() => setSpawning((s) => !s)}
                className="text-xs px-2 py-1 bg-blue-800 hover:bg-blue-700 text-blue-200 rounded"
              >
                Spawn Agent
              </button>
              <button
                onClick={() => setEditing(true)}
                className="text-xs px-2 py-1 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded"
              >
                Edit
              </button>
              <button
                onClick={() => updateMutation.mutate({ is_active: false })}
                disabled={updateMutation.isPending}
                className="text-xs px-2 py-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded disabled:opacity-50"
              >
                Deactivate
              </button>
              <button
                onClick={() => {
                  if (confirm(`Delete persona "${persona.name}"?`)) deleteMutation.mutate()
                }}
                disabled={deleteMutation.isPending}
                className="text-xs px-2 py-1 text-red-500 hover:text-red-400 hover:bg-zinc-800 rounded disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 mt-3">
            <span className="text-xs text-zinc-500 font-mono">{persona.model}</span>
            <span className="text-zinc-700">·</span>
            <span className="text-xs text-zinc-500">temp {persona.temperature.toFixed(1)}</span>
            <span className="text-zinc-700">·</span>
            <span className="text-xs text-zinc-500">{persona.max_tokens} tok</span>
            <span className="text-zinc-700">·</span>
            <div className="flex gap-1">
              {persona.enabled_skills.map((s) => (
                <span
                  key={s}
                  className="text-xs px-1.5 py-0.5 bg-zinc-800 text-zinc-400 rounded"
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        </>
      )}

      {spawning && !editing && (
        <SpawnPanel
          persona={persona}
          activeProjectId={activeProjectId}
          onClose={() => setSpawning(false)}
        />
      )}
    </div>
  )
}

// ── Session card ──────────────────────────────────────────────────────────────

interface SessionCardProps {
  session: import('@/types/api').AgentSession
}

function SessionCard({ session }: SessionCardProps) {
  const isActive = ['queued', 'running', 'waiting'].includes(session.status)
  const elapsed = useElapsed(session.started_at, session.status === 'running' || session.status === 'waiting')
  const [halting, setHalting] = useState(false)
  const qc = useQueryClient()

  async function handleHalt() {
    if (!confirm(`Halt agent session for "${session.persona_name}"?`)) return
    setHalting(true)
    try {
      await haltSession(session.session_uuid)
      toast.info(`Halting ${session.persona_name}…`)
      void qc.invalidateQueries({ queryKey: ['sessions'] })
    } catch {
      toast.error('Failed to halt session')
    } finally {
      setHalting(false)
    }
  }

  return (
    <div className="border border-zinc-800 rounded-lg p-3 text-xs">
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-medium text-zinc-300">{session.persona_name}</span>
        <div className="flex items-center gap-2">
          <StatusBadge status={session.status} />
          {isActive && (
            <button
              onClick={() => void handleHalt()}
              disabled={halting}
              className="text-xs px-1.5 py-0.5 text-red-500 hover:text-red-400
                         hover:bg-zinc-800 rounded disabled:opacity-50"
            >
              Halt
            </button>
          )}
        </div>
      </div>
      <p className="text-zinc-500 truncate mb-1.5">{session.task}</p>
      <div className="flex items-center gap-3 text-zinc-600">
        {elapsed && <span>{elapsed}</span>}
        {session.total_tokens > 0 && <span>{session.total_tokens.toLocaleString()} tokens</span>}
        <span className="font-mono text-zinc-700">{session.model_snapshot}</span>
      </div>
      {session.error_message && (
        <p className="mt-1.5 text-red-400 text-xs line-clamp-2">{session.error_message}</p>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Agents() {
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)

  const personasQuery = useQuery({
    queryKey: ['personas'],
    queryFn: () => listPersonas(true),
  })

  const sessionsQuery = useQuery({
    queryKey: ['sessions', activeProjectId, 'active'],
    queryFn: () => listSessions(activeProjectId ?? undefined),
    refetchInterval: 10_000,
    enabled: activeProjectId !== null,
  })

  const createMutation = useMutation({
    mutationFn: (data: PersonaCreate) => createPersona(data),
    onSuccess: () => {
      toast.success('Persona created')
      setShowCreate(false)
      void qc.invalidateQueries({ queryKey: ['personas'] })
    },
    onError: () => toast.error('Failed to create persona'),
  })

  const activeSessions = sessionsQuery.data?.filter((s) =>
    ['queued', 'running', 'waiting'].includes(s.status),
  ) ?? []

  const historySessions = sessionsQuery.data?.filter((s) =>
    ['completed', 'failed', 'halted'].includes(s.status),
  ) ?? []

  const [showHistory, setShowHistory] = useState(false)

  return (
    <div className="p-6 h-full overflow-y-auto">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Agents</h1>
      </div>

      {/* ── Personas ── */}
      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-zinc-400">Personas</h2>
          <button
            onClick={() => setShowCreate((s) => !s)}
            className="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded"
          >
            {showCreate ? 'Cancel' : '+ New Persona'}
          </button>
        </div>

        {showCreate && (
          <div className="mb-4">
            <PersonaForm
              onSave={(data) => createMutation.mutate(data as PersonaCreate)}
              onCancel={() => setShowCreate(false)}
              saving={createMutation.isPending}
            />
          </div>
        )}

        {personasQuery.isLoading && (
          <p className="text-sm text-zinc-500">Loading personas…</p>
        )}

        {personasQuery.data?.length === 0 && !showCreate && (
          <p className="text-sm text-zinc-600">
            No personas yet. Create one to start spawning agents.
          </p>
        )}

        <div className="flex flex-col gap-3">
          {personasQuery.data?.map((persona) => (
            <PersonaCard
              key={persona.id}
              persona={persona}
              activeProjectId={activeProjectId}
              onEdited={() => void qc.invalidateQueries({ queryKey: ['personas'] })}
            />
          ))}
        </div>
      </section>

      {/* ── Active Sessions ── */}
      <section>
        <h2 className="text-sm font-medium text-zinc-400 mb-3">
          Active Sessions
          {activeSessions.length > 0 && (
            <span className="ml-2 text-zinc-500">({activeSessions.length})</span>
          )}
        </h2>

        {activeProjectId === null && (
          <p className="text-sm text-zinc-600">Select a project to see sessions.</p>
        )}

        {activeProjectId !== null && activeSessions.length === 0 && !sessionsQuery.isLoading && (
          <p className="text-sm text-zinc-600">No active sessions.</p>
        )}

        <div className="flex flex-col gap-2 mb-4">
          {activeSessions.map((s) => (
            <SessionCard key={s.session_uuid} session={s} />
          ))}
        </div>

        {/* History — collapsible */}
        {historySessions.length > 0 && (
          <div>
            <button
              onClick={() => setShowHistory((v) => !v)}
              className="text-xs text-zinc-500 hover:text-zinc-300 mb-2"
            >
              {showHistory ? '▾' : '▸'} History ({historySessions.length})
            </button>
            {showHistory && (
              <div className="flex flex-col gap-2">
                {historySessions.map((s) => (
                  <SessionCard key={s.session_uuid} session={s} />
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
