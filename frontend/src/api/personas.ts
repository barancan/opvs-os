import { apiClient } from './client'
import type { Persona, PersonaCreate, PersonaUpdate } from '@/types/api'

export const listPersonas = (activeOnly = true): Promise<Persona[]> =>
  apiClient.get<Persona[]>(`/api/personas?active_only=${activeOnly}`)

export const createPersona = (data: PersonaCreate): Promise<Persona> =>
  apiClient.post<Persona>('/api/personas', data)

export const updatePersona = (id: number, data: PersonaUpdate): Promise<Persona> =>
  apiClient.put<Persona>(`/api/personas/${id}`, data)

export const deletePersona = (id: number): Promise<{ deleted: boolean }> =>
  apiClient.delete<{ deleted: boolean }>(`/api/personas/${id}`)
