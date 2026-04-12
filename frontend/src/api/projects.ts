import { apiClient } from './client'
import type {
  LinearLink,
  LinearLinkCreate,
  Project,
  ProjectCreate,
  ProjectStatus,
  ProjectUpdate,
} from '@/types/api'

export const listProjects = (status?: ProjectStatus): Promise<Project[]> =>
  apiClient.get<Project[]>(status ? `/api/projects?status=${status}` : '/api/projects')

export const getProject = (id: number): Promise<Project> =>
  apiClient.get<Project>(`/api/projects/${id}`)

export const createProject = (data: ProjectCreate): Promise<Project> =>
  apiClient.post<Project>('/api/projects', data)

export const updateProject = (id: number, data: ProjectUpdate): Promise<Project> =>
  apiClient.put<Project>(`/api/projects/${id}`, data)

export const addLinearLink = (
  projectId: number,
  data: LinearLinkCreate,
): Promise<LinearLink> =>
  apiClient.post<LinearLink>(`/api/projects/${projectId}/linear-links`, data)

export const removeLinearLink = (
  projectId: number,
  linkId: number,
): Promise<{ deleted: boolean }> =>
  apiClient.delete<{ deleted: boolean }>(
    `/api/projects/${projectId}/linear-links/${linkId}`,
  )
