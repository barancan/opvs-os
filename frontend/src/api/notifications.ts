import { apiClient } from './client'
import type { Notification, NotificationStatus } from '@/types/api'

export const getNotifications = (status?: NotificationStatus): Promise<Notification[]> =>
  apiClient.get<Notification[]>(
    status ? `/api/notifications?status=${status}` : '/api/notifications'
  )

export const updateNotificationStatus = (
  id: number,
  status: NotificationStatus
): Promise<Notification> =>
  apiClient.put<Notification>(`/api/notifications/${id}/status`, { status })

export const deleteNotification = (id: number): Promise<{ deleted: boolean }> =>
  apiClient.delete<{ deleted: boolean }>(`/api/notifications/${id}`)
