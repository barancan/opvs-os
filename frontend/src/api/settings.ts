import { ApiError, apiClient } from '@/api/client'
import type { ConnectionTestResult, Setting, SettingUpdate } from '@/types/api'

export function getSettings(): Promise<Setting[]> {
  return apiClient.get<Setting[]>('/api/settings/')
}

export function getSetting(key: string): Promise<Setting> {
  return apiClient.get<Setting>(`/api/settings/${key}`)
}

export async function getSettingOrNull(key: string): Promise<Setting | null> {
  try {
    return await apiClient.get<Setting>(`/api/settings/${key}`)
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }
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
