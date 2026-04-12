import { create } from 'zustand'

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
}

export const useAppStore = create<AppState>()((set) => ({
  wsStatus: 'disconnected',
  setWsStatus: (status) => set({ wsStatus: status }),
  connectionStatuses: {},
  setConnectionStatus: (service, state) =>
    set((s) => ({ connectionStatuses: { ...s.connectionStatuses, [service]: state } })),
}))
