import { create } from 'zustand'

type WsStatus = 'connecting' | 'connected' | 'disconnected'

interface AppState {
  wsStatus: WsStatus
  setWsStatus: (status: WsStatus) => void
}

export const useAppStore = create<AppState>()((set) => ({
  wsStatus: 'disconnected',
  setWsStatus: (status) => set({ wsStatus: status }),
}))
