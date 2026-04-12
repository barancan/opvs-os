import { apiClient } from './client'
import type { ChatMessage, ChatRequest, CompactStatus } from '@/types/api'

export const getChatHistory = (projectId?: number): Promise<ChatMessage[]> =>
  apiClient.get<ChatMessage[]>(
    projectId !== undefined
      ? `/api/chat/history?project_id=${projectId}`
      : '/api/chat/history',
  )

export const sendMessage = (
  content: string,
  clientId: string,
  projectId?: number,
): Promise<ChatMessage> => {
  const params = new URLSearchParams({ client_id: clientId })
  if (projectId !== undefined) params.set('project_id', String(projectId))
  return apiClient.post<ChatMessage>(`/api/chat?${params.toString()}`, {
    content,
  } satisfies ChatRequest)
}

export const clearChatHistory = (): Promise<{ cleared: boolean }> =>
  apiClient.delete<{ cleared: boolean }>('/api/chat/history')

export const getCompactStatus = (): Promise<CompactStatus> =>
  apiClient.get<CompactStatus>('/api/chat/compact')

export const approveToolAction = (requestId: string): Promise<{ status: string; request_id: string }> =>
  apiClient.post<{ status: string; request_id: string }>(`/api/chat/approve/${requestId}`)

export const rejectToolAction = (requestId: string): Promise<{ status: string; request_id: string }> =>
  apiClient.post<{ status: string; request_id: string }>(`/api/chat/reject/${requestId}`)
