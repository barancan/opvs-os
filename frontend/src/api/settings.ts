import { apiClient } from '@/api/client'
import type { ConnectionTestResult, Setting, SettingUpdate } from '@/types/api'

export function getSettings(): Promise<Setting[]> {
  return apiClient.get<Setting[]>('/api/settings/')
}

export function getSetting(key: string): Promise<Setting> {
  return apiClient.get<Setting>(`/api/settings/${key}`)
}

export function upsertSetting(key: string, data: SettingUpdate): Promise<Setting> {
  return apiClient.put<Setting>(`/api/settings/${key}`, data)
}

export function deleteSetting(key: string): Promise<{ deleted: boolean }> {
  return apiClient.delete<{ deleted: boolean }>(`/api/settings/${key}`)
}

export function testConnection(service: string): Promise<ConnectionTestResult> {
  return apiClient.post<ConnectionTestResult>(`/api/settings/test/${service}`)
}
