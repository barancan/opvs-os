import { useQuery } from '@tanstack/react-query'
import { listProjects } from '@/api/projects'
import { listSessions } from '@/api/sessions'
import { KillSwitchButton } from '@/components/dashboard/KillSwitchButton'
import { NotificationInbox } from '@/components/dashboard/NotificationInbox'
import { OrchestratorChat } from '@/components/dashboard/OrchestratorChat'
import { useAppStore } from '@/stores/useAppStore'
import type { SessionStatus } from '@/types/api'

// ── StatusBadge ───────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<SessionStatus, string> = {
  queued: 'text-zinc-400',
  running: 'text-green-400',
  waiting: 'text-amber-400 animate-pulse',
  completed: 'text-zinc-600',
  failed: 'text-red-400',
  halted: 'text-zinc-600',
}

function StatusBadge({ status }: { status: SessionStatus }) {
  return (
    <span className={`text-xs ${STATUS_COLORS[status]}`}>{status}</span>
  )
}

// ── ActiveAgentsMini ──────────────────────────────────────────────────────────

function ActiveAgentsMini({ projectId }: { projectId: number | null }) {
  const { data: sessions } = useQuery({
    queryKey: ['sessions', projectId, 'active'],
    queryFn: () => listSessions(projectId ?? undefined),
    enabled: projectId !== null,
    refetchInterval: 10_000,
  })

  const active = sessions?.filter((s) =>
    ['queued', 'running', 'waiting'].includes(s.status),
  ) ?? []

  if (projectId === null) {
    return <p className="text-xs text-zinc-600">Select a project to see agents.</p>
  }

  if (active.length === 0) {
    return <p className="text-xs text-zinc-600">No active agents.</p>
  }

  return (
    <div className="flex flex-col gap-2">
      {active.map((session) => (
        <div key={session.session_uuid} className="text-xs border border-zinc-800 rounded p-2">
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-zinc-300 truncate">{session.persona_name}</span>
            <StatusBadge status={session.status} />
          </div>
          <p className="text-zinc-500 truncate">{session.task}</p>
        </div>
      ))}
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const activeProjectId = useAppStore((s) => s.activeProjectId)

  const { data: projects } = useQuery({
    queryKey: ['projects', 'active'],
    queryFn: () => listProjects('active'),
  })

  const activeProject = projects?.find((p) => p.id === activeProjectId)

  return (
    <div className="flex flex-col h-full p-6 gap-4 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <h1 className="text-xl font-semibold text-zinc-100">
          {activeProject?.name ?? 'Dashboard'}
        </h1>
        <KillSwitchButton />
      </div>

      {/* Main content — takes remaining space above chat */}
      <div className="flex gap-4 flex-1 min-h-0 overflow-hidden">
        {/* Notifications — left, 60% width */}
        <div className="flex-[3] overflow-y-auto min-h-0">
          <NotificationInbox />
        </div>

        {/* Active Agents — right, 40% width */}
        <div className="flex-[2] rounded-lg border border-zinc-800 p-4 overflow-y-auto">
          <h2 className="text-sm font-medium text-zinc-400 mb-3">Active Agents</h2>
          <ActiveAgentsMini projectId={activeProjectId} />
        </div>
      </div>

      {/* Chat — pinned at bottom, fixed height */}
      <div className="flex-shrink-0">
        <OrchestratorChat />
      </div>
    </div>
  )
}
