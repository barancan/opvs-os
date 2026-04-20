import { useEffect } from 'react'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { toast } from 'sonner'
import { listProjects } from '@/api/projects'
import { Toaster } from '@/components/ui/sonner'
import { AppShell } from '@/components/layout/AppShell'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAppStore } from '@/stores/useAppStore'
import type { AgentMessage, SessionStatus, ToolApprovalRequest } from '@/types/api'
import Agents from '@/pages/Agents'
import Analytics from '@/pages/Analytics'
import Brain from '@/pages/Brain'
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
  const addToolApproval = useAppStore((s) => s.addToolApproval)
  const updateToolApproval = useAppStore((s) => s.updateToolApproval)
  const clearToolApprovals = useAppStore((s) => s.clearToolApprovals)
  const addRunningJob = useAppStore((s) => s.addRunningJob)
  const removeRunningJob = useAppStore((s) => s.removeRunningJob)
  const updateSessionStatus = useAppStore((s) => s.updateSessionStatus)
  const addChatroomMessage = useAppStore((s) => s.addChatroomMessage)

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
      clearToolApprovals()
      void qc.invalidateQueries({ queryKey: ['chatHistory'] })
    },
    chat_error: () => {
      setIsStreaming(false)
      clearStreamingContent()
    },
    notification_created: () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] })
    },
    notification_updated: () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] })
    },
    tool_approval_required: (payload: unknown) => {
      const approval = payload as ToolApprovalRequest
      addToolApproval({ ...approval, status: 'pending' })
    },
    tool_result: (payload: unknown) => {
      const { tool_name, success, content } = payload as {
        tool_name: string
        success: boolean
        content: string
      }
      const approvals = useAppStore.getState().toolApprovals
      const entry = Object.values(approvals).find(
        (a) => a.tool_name === tool_name && a.status === 'executing',
      )
      if (entry) {
        updateToolApproval(entry.request_id, {
          status: success ? 'done' : 'failed',
          result: content,
        })
      }
    },
    job_started: (payload: unknown) => {
      const { job_id } = payload as { job_id: number; project_id: number }
      addRunningJob(job_id)
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      toast.info(`Job #${job_id} started`)
    },
    job_completed: (payload: unknown) => {
      const { job_id } = payload as { job_id: number }
      removeRunningJob(job_id)
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      toast.success(`Job #${job_id} completed — check notifications`)
    },
    job_failed: (payload: unknown) => {
      const { job_id, error } = payload as { job_id: number; error: string }
      removeRunningJob(job_id)
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      toast.error(`Job #${job_id} failed: ${error}`)
    },
    session_started: () => {
      void qc.invalidateQueries({ queryKey: ['sessions'] })
    },
    session_completed: (payload: unknown) => {
      const { session_uuid } = payload as { session_uuid: string }
      updateSessionStatus(session_uuid, 'completed' as SessionStatus)
      void qc.invalidateQueries({ queryKey: ['sessions'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
    },
    session_failed: (payload: unknown) => {
      const { session_uuid } = payload as { session_uuid: string }
      updateSessionStatus(session_uuid, 'failed' as SessionStatus)
      void qc.invalidateQueries({ queryKey: ['sessions'] })
    },
    session_halted: (payload: unknown) => {
      const { session_uuid } = payload as { session_uuid: string }
      updateSessionStatus(session_uuid, 'halted' as SessionStatus)
      void qc.invalidateQueries({ queryKey: ['sessions'] })
    },
    agent_message: (payload: unknown) => {
      addChatroomMessage(payload as AgentMessage)
    },
  })

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/brain" element={<Brain />} />
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
