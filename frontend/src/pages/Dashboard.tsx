import { useQuery } from '@tanstack/react-query'
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle, useDefaultLayout } from 'react-resizable-panels'
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

  const verticalLayout = useDefaultLayout({ id: 'dashboard-vertical', storage: localStorage })
  const horizontalLayout = useDefaultLayout({ id: 'dashboard-horizontal', storage: localStorage })

  return (
    <div className="flex flex-col h-full p-4 gap-3 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <h1 className="text-xl font-semibold text-zinc-100">
          {activeProject?.name ?? 'Dashboard'}
        </h1>
        <KillSwitchButton />
      </div>

      {/* Resizable main area */}
      <PanelGroup
        orientation="vertical"
        className="flex-1 min-h-0"
        defaultLayout={verticalLayout.defaultLayout}
        onLayoutChanged={verticalLayout.onLayoutChanged}
      >

        {/* Top row: Notifications + Active Agents */}
        <Panel defaultSize={55} minSize={20}>
          <PanelGroup
            orientation="horizontal"
            className="h-full"
            defaultLayout={horizontalLayout.defaultLayout}
            onLayoutChanged={horizontalLayout.onLayoutChanged}
          >

            {/* Notifications */}
            <Panel defaultSize={60} minSize={20}>
              <div className="h-full overflow-y-auto pr-1">
                <NotificationInbox />
              </div>
            </Panel>

            <PanelResizeHandle className="group relative w-1.5 mx-1 cursor-col-resize">
              <div className="absolute inset-0 rounded-full bg-zinc-800 group-hover:bg-zinc-500 transition-colors" />
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-0.5 opacity-0 group-hover:opacity-100">
                <div className="w-0.5 h-0.5 rounded-full bg-zinc-400" />
                <div className="w-0.5 h-0.5 rounded-full bg-zinc-400" />
                <div className="w-0.5 h-0.5 rounded-full bg-zinc-400" />
              </div>
            </PanelResizeHandle>

            {/* Active Agents */}
            <Panel defaultSize={40} minSize={15}>
              <div className="h-full border border-zinc-800 rounded-lg p-3 overflow-y-auto">
                <h2 className="text-xs font-medium text-zinc-400 mb-2">Active Agents</h2>
                <ActiveAgentsMini projectId={activeProjectId} />
              </div>
            </Panel>

          </PanelGroup>
        </Panel>

        <PanelResizeHandle className="group relative h-1.5 my-1 cursor-row-resize">
          <div className="absolute inset-0 rounded-full bg-zinc-800 group-hover:bg-zinc-500 transition-colors" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-row gap-0.5 opacity-0 group-hover:opacity-100">
            <div className="w-0.5 h-0.5 rounded-full bg-zinc-400" />
            <div className="w-0.5 h-0.5 rounded-full bg-zinc-400" />
            <div className="w-0.5 h-0.5 rounded-full bg-zinc-400" />
          </div>
        </PanelResizeHandle>

        {/* Bottom: Orchestrator Chat */}
        <Panel defaultSize={45} minSize={20}>
          <div className="h-full">
            <OrchestratorChat />
          </div>
        </Panel>

      </PanelGroup>
    </div>
  )
}
