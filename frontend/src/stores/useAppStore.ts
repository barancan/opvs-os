import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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

  // Active project (persisted to localStorage)
  activeProjectId: number | null
  setActiveProjectId: (id: number | null) => void
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

      // Active project
      activeProjectId: null,
      setActiveProjectId: (id) => set({ activeProjectId: id }),
    }),
    {
      name: 'opvs-app-store',
      // Only persist activeProjectId — runtime state must reset on page load
      partialize: (state) => ({ activeProjectId: state.activeProjectId }),
    },
  ),
)
