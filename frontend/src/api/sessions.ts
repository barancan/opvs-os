import { apiClient } from './client'
import type { AgentMessage, AgentSession, SessionStatus } from '@/types/api'

export const listSessions = (projectId?: number, status?: SessionStatus): Promise<AgentSession[]> => {
  const params = new URLSearchParams()
  if (projectId !== undefined) params.set('project_id', String(projectId))
  if (status) params.set('status', status)
  const qs = params.toString()
  return apiClient.get<AgentSession[]>(`/api/sessions${qs ? `?${qs}` : ''}`)
}

export const spawnSession = (
  projectId: number,
  personaId: number,
  task: string,
): Promise<AgentSession> =>
  apiClient.post<AgentSession>('/api/sessions', {
    project_id: projectId,
    persona_id: personaId,
    task,
  })

export const haltSession = (sessionUuid: string): Promise<{ status: string }> =>
  apiClient.post<{ status: string }>(`/api/sessions/${sessionUuid}/halt`)

export const getChatroomMessages = (projectId: number): Promise<AgentMessage[]> =>
  apiClient.get<AgentMessage[]>(`/api/sessions/chatroom/messages?project_id=${projectId}`)

export const postChatroomReply = (
  projectId: number,
  content: string,
  replyToId?: number,
  sessionUuid?: string,
): Promise<AgentMessage> =>
  apiClient.post<AgentMessage>('/api/sessions/chatroom/reply', {
    project_id: projectId,
    content,
    reply_to_id: replyToId ?? null,
    session_uuid: sessionUuid ?? null,
    sender_type: 'user',
    sender_name: 'You',
  })
