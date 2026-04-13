import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AgentMessage, AgentSession, SessionStatus, ToolApprovalState } from '@/types/api'

type WsStatus = 'connecting' | 'connected' | 'disconnected'

type ConnectionStatus = 'untested' | 'ok' | 'error'

interface ServiceConnectionState {
  status: ConnectionStatus
  error?: string
}

interface AppState {
  wsStatus: WsStatus
  setWsStatus: (status: WsStatus) => void
  connectionStatuses: Record<string, ServiceConnectionState>
  setConnectionStatus: (service: string, state: ServiceConnectionState) => void

  // Kill switch
  killSwitchActive: boolean
  killSwitchArmed: boolean
  setKillSwitchActive: (active: boolean) => void
  setKillSwitchArmed: (armed: boolean) => void

  // Chat streaming (runtime only — not persisted)
  streamingContent: string
  isStreaming: boolean
  appendStreamToken: (token: string) => void
  clearStreamingContent: () => void
  setIsStreaming: (streaming: boolean) => void

  // Tool approvals (runtime only — not persisted)
  toolApprovals: Record<string, ToolApprovalState>
  addToolApproval: (approval: ToolApprovalState) => void
  updateToolApproval: (requestId: string, updates: Partial<ToolApprovalState>) => void
  clearToolApprovals: () => void

  // Running jobs (runtime only — not persisted)
  runningJobIds: number[]
  addRunningJob: (id: number) => void
  removeRunningJob: (id: number) => void

  // Active project (persisted to localStorage)
  activeProjectId: number | null
  setActiveProjectId: (id: number | null) => void

  // Active agent sessions (runtime only — not persisted)
  activeSessions: AgentSession[]
  setActiveSessions: (sessions: AgentSession[]) => void
  updateSessionStatus: (uuid: string, status: SessionStatus) => void

  // Chatroom messages (runtime only — not persisted)
  chatroomMessages: AgentMessage[]
  addChatroomMessage: (msg: AgentMessage) => void
  clearChatroomMessages: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      wsStatus: 'disconnected',
      setWsStatus: (status) => set({ wsStatus: status }),
      connectionStatuses: {},
      setConnectionStatus: (service, state) =>
        set((s) => ({
          connectionStatuses: { ...s.connectionStatuses, [service]: state },
        })),

      // Kill switch
      killSwitchActive: false,
      killSwitchArmed: false,
      setKillSwitchActive: (active) => set({ killSwitchActive: active }),
      setKillSwitchArmed: (armed) => set({ killSwitchArmed: armed }),

      // Chat streaming
      streamingContent: '',
      isStreaming: false,
      appendStreamToken: (token) =>
        set((s) => ({ streamingContent: s.streamingContent + token })),
      clearStreamingContent: () => set({ streamingContent: '' }),
      setIsStreaming: (streaming) => set({ isStreaming: streaming }),

      // Tool approvals
      toolApprovals: {},
      addToolApproval: (approval) =>
        set((s) => ({
          toolApprovals: { ...s.toolApprovals, [approval.request_id]: approval },
        })),
      updateToolApproval: (requestId, updates) =>
        set((s) => ({
          toolApprovals: {
            ...s.toolApprovals,
            [requestId]: { ...s.toolApprovals[requestId], ...updates },
          },
        })),
      clearToolApprovals: () => set({ toolApprovals: {} }),

      // Running jobs
      runningJobIds: [],
      addRunningJob: (id) =>
        set((s) => ({
          runningJobIds: s.runningJobIds.includes(id) ? s.runningJobIds : [...s.runningJobIds, id],
        })),
      removeRunningJob: (id) =>
        set((s) => ({ runningJobIds: s.runningJobIds.filter((j) => j !== id) })),

      // Active project
      activeProjectId: null,
      setActiveProjectId: (id) => set({ activeProjectId: id }),

      // Active sessions
      activeSessions: [],
      setActiveSessions: (sessions) => set({ activeSessions: sessions }),
      updateSessionStatus: (uuid, status) =>
        set((s) => ({
          activeSessions: s.activeSessions.map((sess) =>
            sess.session_uuid === uuid ? { ...sess, status } : sess,
          ),
        })),

      // Chatroom messages
      chatroomMessages: [],
      addChatroomMessage: (msg) =>
        set((s) => ({
          // Deduplicate by id
          chatroomMessages: s.chatroomMessages.some((m) => m.id === msg.id)
            ? s.chatroomMessages
            : [...s.chatroomMessages, msg],
        })),
      clearChatroomMessages: () => set({ chatroomMessages: [] }),
    }),
    {
      name: 'opvs-app-store',
      // Only persist activeProjectId — runtime state must reset on page load
      partialize: (state) => ({ activeProjectId: state.activeProjectId }),
    },
  ),
)
