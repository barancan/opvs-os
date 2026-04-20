import { Outlet, useLocation } from 'react-router-dom'
import { ChatroomPanel } from '@/components/layout/ChatroomPanel'
import { Sidebar } from '@/components/layout/Sidebar'

export function AppShell() {
  const location = useLocation()
  const showChatroom = !['/settings', '/analytics', '/brain'].includes(location.pathname)

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <main className="flex-1 h-full overflow-hidden">
        <Outlet />
      </main>
      {showChatroom && <ChatroomPanel />}
    </div>
  )
}
