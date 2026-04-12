import { KillSwitchButton } from '@/components/dashboard/KillSwitchButton'
import { NotificationInbox } from '@/components/dashboard/NotificationInbox'
import { OrchestratorChat } from '@/components/dashboard/OrchestratorChat'

export default function Dashboard() {
  return (
    <div className="flex flex-col h-full p-6 gap-4 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <h1 className="text-xl font-semibold text-zinc-100">Dashboard</h1>
        <KillSwitchButton />
      </div>

      {/* Main content — takes remaining space above chat */}
      <div className="flex gap-4 flex-1 min-h-0 overflow-hidden">
        {/* Notifications — left, 60% width */}
        <div className="flex-[3] overflow-y-auto min-h-0">
          <NotificationInbox />
        </div>

        {/* Active Agents — right, 40% width, placeholder */}
        <div className="flex-[2] rounded-lg border border-zinc-800 p-4">
          <h2 className="text-sm font-medium text-zinc-400 mb-3">Active Agents</h2>
          <p className="text-xs text-zinc-600">Agent management comes in Phase 3.</p>
        </div>
      </div>

      {/* Chat — pinned at bottom, fixed height */}
      <div className="flex-shrink-0">
        <OrchestratorChat />
      </div>
    </div>
  )
}
