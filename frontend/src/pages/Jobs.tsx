import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Pause, Pencil, Play, Plus, X } from 'lucide-react'
import { toast } from 'sonner'
import { createJob, deleteJob, listJobs, runJobNow, updateJob } from '@/api/jobs'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/useAppStore'
import type { ScheduledJob, ScheduledJobCreate, ScheduledJobUpdate } from '@/types/api'

// ---------------------------------------------------------------------------
// Cron helper
// ---------------------------------------------------------------------------

function describeCron(cron: string): string {
  const parts = cron.split(' ')
  if (parts.length !== 5) return cron
  const [minute, hour, , , weekday] = parts
  if (weekday === '*' && minute !== '*' && hour !== '*') {
    const h = parseInt(hour)
    const m = parseInt(minute)
    const time = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
    return `Daily at ${time}`
  }
  if (weekday !== '*' && minute !== '*' && hour !== '*') {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    const day = days[parseInt(weekday)] ?? weekday
    return `Weekly ${day} at ${hour}:${minute.padStart(2, '0')}`
  }
  return cron
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ---------------------------------------------------------------------------
// Preset schedules
// ---------------------------------------------------------------------------

interface CronPreset {
  label: string
  cron: string
  timezone: string
}

const PRESETS: CronPreset[] = [
  { label: 'Daily at 07:00 CET', cron: '0 7 * * *', timezone: 'Europe/Amsterdam' },
  { label: 'Daily at 09:00 UTC', cron: '0 9 * * *', timezone: 'UTC' },
  { label: 'Weekly Monday 08:00 CET', cron: '0 8 * * 1', timezone: 'Europe/Amsterdam' },
  { label: 'Hourly', cron: '0 * * * *', timezone: 'UTC' },
]

// ---------------------------------------------------------------------------
// Create / Edit form
// ---------------------------------------------------------------------------

interface JobFormProps {
  projectId: number
  initial?: ScheduledJob
  onDone: () => void
}

function JobForm({ projectId, initial, onDone }: JobFormProps) {
  const qc = useQueryClient()
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [scheduleMode, setScheduleMode] = useState<'preset' | 'custom'>(
    initial ? 'custom' : 'preset',
  )
  const [selectedPreset, setSelectedPreset] = useState<number>(0)
  const [cron, setCron] = useState(initial?.cron ?? PRESETS[0].cron)
  const [timezone, setTimezone] = useState(initial?.timezone ?? PRESETS[0].timezone)
  const [prompt, setPrompt] = useState(initial?.prompt ?? '')

  const isEdit = initial !== undefined

  const createMutation = useMutation({
    mutationFn: (data: ScheduledJobCreate) => createJob(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Job created')
      onDone()
    },
    onError: (err) =>
      toast.error(`Failed to create job: ${err instanceof Error ? err.message : String(err)}`),
  })

  const updateMutation = useMutation({
    mutationFn: (data: ScheduledJobUpdate) => updateJob(initial!.id, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Job updated')
      onDone()
    },
    onError: (err) =>
      toast.error(`Failed to update job: ${err instanceof Error ? err.message : String(err)}`),
  })

  const handlePresetChange = (idx: number) => {
    setSelectedPreset(idx)
    const preset = PRESETS[idx]
    if (preset) {
      setCron(preset.cron)
      setTimezone(preset.timezone)
    }
  }

  const handleSubmit = () => {
    if (!name.trim() || !prompt.trim()) return
    if (isEdit) {
      updateMutation.mutate({ name: name.trim(), description: description.trim() || undefined, cron, timezone, prompt: prompt.trim() })
    } else {
      createMutation.mutate({ project_id: projectId, name: name.trim(), description: description.trim() || undefined, cron, timezone, prompt: prompt.trim() })
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending
  const canSubmit = name.trim().length > 0 && prompt.trim().length > 0 && !isPending

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/60 p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-200">{isEdit ? 'Edit job' : 'New job'}</span>
        <button onClick={onDone} className="text-zinc-500 hover:text-zinc-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Name */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-zinc-400">Name *</label>
        <input
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
          placeholder="Daily report"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      {/* Description */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-zinc-400">Description</label>
        <textarea
          rows={2}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none resize-none"
          placeholder="What this job does"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      {/* Schedule mode toggle */}
      <div className="flex flex-col gap-2">
        <label className="text-xs text-zinc-400">Schedule</label>
        <div className="flex gap-1 rounded-md border border-zinc-700 bg-zinc-900 p-0.5 w-fit">
          {(['preset', 'custom'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setScheduleMode(mode)}
              className={[
                'px-3 py-1 text-xs rounded transition-colors',
                scheduleMode === mode
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'text-zinc-500 hover:text-zinc-300',
              ].join(' ')}
            >
              {mode === 'preset' ? 'Common schedules' : 'Custom cron'}
            </button>
          ))}
        </div>

        {scheduleMode === 'preset' ? (
          <div className="flex flex-col gap-2">
            <select
              className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 focus:border-zinc-500 focus:outline-none"
              value={selectedPreset}
              onChange={(e) => handlePresetChange(Number(e.target.value))}
            >
              {PRESETS.map((p, i) => (
                <option key={i} value={i}>
                  {p.label}
                </option>
              ))}
            </select>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-zinc-400">Timezone</label>
              <input
                className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 focus:border-zinc-500 focus:outline-none"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              />
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-xs text-zinc-400">Cron expression</label>
              <input
                className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm font-mono text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
                placeholder="0 7 * * *"
                value={cron}
                onChange={(e) => setCron(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1 w-40">
              <label className="text-xs text-zinc-400">Timezone</label>
              <input
                className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none"
                placeholder="UTC"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Prompt */}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-zinc-400">Prompt *</label>
        <textarea
          rows={4}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none resize-none"
          placeholder="Fetch my Linear projects and summarize today's priorities and blockers."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </div>

      <Button onClick={handleSubmit} disabled={!canSubmit} size="sm" className="self-end">
        {isPending ? (isEdit ? 'Saving…' : 'Creating…') : isEdit ? 'Save' : 'Create'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Job card
// ---------------------------------------------------------------------------

interface JobCardProps {
  job: ScheduledJob
  isRunning: boolean
}

function JobCard({ job, isRunning }: JobCardProps) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)

  const runMutation = useMutation({
    mutationFn: () => runJobNow(job.id),
    onSuccess: () => toast.success('Job triggered'),
    onError: (err) =>
      toast.error(`Run failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const pauseMutation = useMutation({
    mutationFn: () => updateJob(job.id, { status: 'paused' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Job paused')
    },
    onError: (err) =>
      toast.error(`Pause failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteJob(job.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Job deleted')
    },
    onError: (err) =>
      toast.error(`Delete failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const lastRunDot = () => {
    if (!job.last_run_status) return null
    if (job.last_run_status === 'success') return <span className="text-green-400">✓</span>
    if (job.last_run_status === 'failed') return <span className="text-red-400">✗</span>
    if (job.last_run_status === 'running') return <span className="text-amber-400">◌</span>
    return null
  }

  if (editing) {
    return (
      <JobForm
        projectId={job.project_id}
        initial={job}
        onDone={() => setEditing(false)}
      />
    )
  }

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-zinc-100 truncate">{job.name}</span>
            {isRunning && (
              <span className="animate-pulse text-xs text-amber-400 font-medium">Running…</span>
            )}
          </div>
          {job.description && (
            <span className="text-xs text-zinc-500 truncate">{job.description}</span>
          )}
          <div className="mt-1 flex items-center gap-2 text-xs text-zinc-400">
            <span className="font-mono">{describeCron(job.cron)}</span>
            <span className="text-zinc-600">·</span>
            <span>{job.timezone}</span>
          </div>
          {job.last_run_at && (
            <div className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500">
              <span>Last run: {relativeTime(job.last_run_at)}</span>
              {lastRunDot()}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            title="Run now"
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100 disabled:opacity-40 transition-colors"
          >
            <Play className="h-3 w-3" />
            Run
          </button>
          <button
            onClick={() => setEditing(true)}
            title="Edit"
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
          >
            <Pencil className="h-3 w-3" />
            Edit
          </button>
          <button
            onClick={() => pauseMutation.mutate()}
            disabled={pauseMutation.isPending}
            title="Pause"
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100 disabled:opacity-40 transition-colors"
          >
            <Pause className="h-3 w-3" />
          </button>
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            title="Delete"
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-700 hover:text-red-400 disabled:opacity-40 transition-colors"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Paused job row
// ---------------------------------------------------------------------------

function PausedJobRow({ job }: { job: ScheduledJob }) {
  const qc = useQueryClient()

  const resumeMutation = useMutation({
    mutationFn: () => updateJob(job.id, { status: 'active' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      toast.success('Job resumed')
    },
    onError: (err) =>
      toast.error(`Resume failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteJob(job.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (err) =>
      toast.error(`Delete failed: ${err instanceof Error ? err.message : String(err)}`),
  })

  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-800/20 px-4 py-3">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-sm text-zinc-400 truncate">{job.name}</span>
        <span className="text-xs text-zinc-600 font-mono">{describeCron(job.cron)} · {job.timezone}</span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={() => resumeMutation.mutate()}
          disabled={resumeMutation.isPending}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100 disabled:opacity-40 transition-colors"
        >
          <Play className="h-3 w-3" />
          Resume
        </button>
        <button
          onClick={() => deleteMutation.mutate()}
          disabled={deleteMutation.isPending}
          className="rounded px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-700 hover:text-red-400 disabled:opacity-40 transition-colors"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Jobs() {
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const runningJobIds = useAppStore((s) => s.runningJobIds)
  const [showCreate, setShowCreate] = useState(false)
  const [showPaused, setShowPaused] = useState(false)

  const activeJobsQuery = useQuery({
    queryKey: ['jobs', activeProjectId, 'active'],
    queryFn: () => listJobs(activeProjectId ?? undefined, 'active'),
    enabled: activeProjectId !== null,
  })

  const pausedJobsQuery = useQuery({
    queryKey: ['jobs', activeProjectId, 'paused'],
    queryFn: () => listJobs(activeProjectId ?? undefined, 'paused'),
    enabled: activeProjectId !== null,
  })

  const activeJobs = activeJobsQuery.data ?? []
  const pausedJobs = pausedJobsQuery.data ?? []

  if (activeProjectId === null) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-500 text-sm">
        No project selected.
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-6 gap-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-zinc-100">Jobs</h1>
        {!showCreate && (
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            New Job
          </Button>
        )}
      </div>

      {/* Create form */}
      {showCreate && (
        <JobForm
          projectId={activeProjectId}
          onDone={() => setShowCreate(false)}
        />
      )}

      {/* Active jobs */}
      {activeJobsQuery.isLoading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : activeJobs.length === 0 && !showCreate ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <p className="text-zinc-500 text-sm">No scheduled jobs yet.</p>
          <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
            Create your first job →
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {activeJobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              isRunning={runningJobIds.includes(job.id)}
            />
          ))}
        </div>
      )}

      {/* Paused jobs section */}
      {pausedJobs.length > 0 && (
        <div className="flex flex-col gap-2">
          <button
            onClick={() => setShowPaused((v) => !v)}
            className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {showPaused ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            Paused ({pausedJobs.length})
          </button>
          {showPaused && (
            <div className="flex flex-col gap-1.5">
              {pausedJobs.map((job) => (
                <PausedJobRow key={job.id} job={job} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
