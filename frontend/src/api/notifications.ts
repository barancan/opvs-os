import { apiClient } from './client'
import type { Notification, NotificationStatus } from '@/types/api'

export const getNotifications = (
  status?: NotificationStatus,
  projectId?: number,
): Promise<Notification[]> => {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (projectId !== undefined) params.set('project_id', String(projectId))
  const qs = params.toString()
  return apiClient.get<Notification[]>(`/api/notifications${qs ? `?${qs}` : ''}`)
}

export const updateNotificationStatus = (
  id: number,
  status: NotificationStatus,
): Promise<Notification> =>
  apiClient.put<Notification>(`/api/notifications/${id}/status`, { status })

export const deleteNotification = (id: number): Promise<{ deleted: boolean }> =>
  apiClient.delete<{ deleted: boolean }>(`/api/notifications/${id}`)
