import { apiClient } from './client'
import type { KillSwitchStatus } from '@/types/api'

export const getKillSwitchStatus = (): Promise<KillSwitchStatus> =>
  apiClient.get<KillSwitchStatus>('/api/killswitch/status')

export const activateKillSwitch = (): Promise<KillSwitchStatus> =>
  apiClient.post<KillSwitchStatus>('/api/killswitch/activate')

export const recoverKillSwitch = (reason: string): Promise<KillSwitchStatus> =>
  apiClient.post<KillSwitchStatus>('/api/killswitch/recover', { reason })
