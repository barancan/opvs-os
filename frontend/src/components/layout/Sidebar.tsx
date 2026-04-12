import { BarChart2, Bot, Clock, FolderOpen, LayoutDashboard, Settings2 } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { ProjectSwitcher } from '@/components/layout/ProjectSwitcher'
import { useAppStore } from '@/stores/useAppStore'

const navItems = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Agents', path: '/agents', icon: Bot },
  { label: 'Jobs', path: '/jobs', icon: Clock },
  { label: 'Projects', path: '/projects', icon: FolderOpen },
  { label: 'Settings', path: '/settings', icon: Settings2 },
  { label: 'Analytics', path: '/analytics', icon: BarChart2 },
]

function WsStatusDot({ status }: { status: 'connecting' | 'connected' | 'disconnected' }) {
  const dotClass =
    status === 'connected'
      ? 'bg-green-500'
      : status === 'connecting'
        ? 'bg-yellow-400'
        : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      <span className="text-xs text-zinc-400 capitalize">{status}</span>
    </div>
  )
}

export function Sidebar() {
  const wsStatus = useAppStore((s) => s.wsStatus)

  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col bg-zinc-900">
      <div className="px-4 py-5">
        <img
          src="/opvs-transparent-white.svg"
          alt="opvs OS"
          className="h-6 w-auto"
        />
      </div>

      {/* Project switcher */}
      <div className="px-2 pb-2">
        <ProjectSwitcher />
      </div>

      <nav className="flex-1 space-y-1 px-2">
        {navItems.map(({ label, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-zinc-800">
        <WsStatusDot status={wsStatus} />
      </div>
    </aside>
  )
}
