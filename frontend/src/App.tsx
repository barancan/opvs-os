import { useEffect } from 'react'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { listProjects } from '@/api/projects'
import { Toaster } from '@/components/ui/sonner'
import { AppShell } from '@/components/layout/AppShell'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAppStore } from '@/stores/useAppStore'
import Agents from '@/pages/Agents'
import Analytics from '@/pages/Analytics'
import Dashboard from '@/pages/Dashboard'
import Jobs from '@/pages/Jobs'
import Projects from '@/pages/Projects'
import Settings from '@/pages/Settings'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

function AppInner() {
  const qc = useQueryClient()
  const setKillSwitchActive = useAppStore((s) => s.setKillSwitchActive)
  const appendStreamToken = useAppStore((s) => s.appendStreamToken)
  const clearStreamingContent = useAppStore((s) => s.clearStreamingContent)
  const setIsStreaming = useAppStore((s) => s.setIsStreaming)
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const setActiveProjectId = useAppStore((s) => s.setActiveProjectId)

  // Bootstrap: ensure activeProjectId always points to a valid active project
  const { data: projects } = useQuery({
    queryKey: ['projects', 'active'],
    queryFn: () => listProjects('active'),
  })

  useEffect(() => {
    if (!projects || projects.length === 0) return
    const isValid = projects.some((p) => p.id === activeProjectId)
    if (!isValid) {
      setActiveProjectId(projects[0].id)
    }
  }, [projects, activeProjectId, setActiveProjectId])

  useWebSocket({
    kill_switch_activated: () => {
      setKillSwitchActive(true)
      void qc.invalidateQueries({ queryKey: ['killswitch'] })
    },
    kill_switch_recovered: () => {
      setKillSwitchActive(false)
      void qc.invalidateQueries({ queryKey: ['killswitch'] })
    },
    chat_token: (payload: unknown) => {
      const { token } = payload as { token: string }
      appendStreamToken(token)
      setIsStreaming(true)
    },
    chat_complete: () => {
      setIsStreaming(false)
      clearStreamingContent()
      // Broad invalidation — matches all ['chatHistory', ...] entries
      void qc.invalidateQueries({ queryKey: ['chatHistory'] })
    },
    chat_error: () => {
      setIsStreaming(false)
      clearStreamingContent()
    },
    notification_created: () => {
      // Broad invalidation — matches all ['notifications', ...] entries
      void qc.invalidateQueries({ queryKey: ['notifications'] })
    },
    notification_updated: () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/analytics" element={<Analytics />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppInner />
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
