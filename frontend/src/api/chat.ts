import { apiClient } from './client'
import type { ChatMessage, ChatRequest, CompactStatus } from '@/types/api'

export const getChatHistory = (): Promise<ChatMessage[]> =>
  apiClient.get<ChatMessage[]>('/api/chat/history')

export const sendMessage = (content: string, clientId: string): Promise<ChatMessage> =>
  apiClient.post<ChatMessage>(`/api/chat?client_id=${encodeURIComponent(clientId)}`, {
    content,
  } satisfies ChatRequest)

export const clearChatHistory = (): Promise<{ cleared: boolean }> =>
  apiClient.delete<{ cleared: boolean }>('/api/chat/history')

export const getCompactStatus = (): Promise<CompactStatus> =>
  apiClient.get<CompactStatus>('/api/chat/compact')
