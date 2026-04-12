import { apiClient } from './client'
import type { ProjectSkill } from '@/types/api'

export const getProjectSkills = (projectId: number): Promise<ProjectSkill[]> =>
  apiClient.get<ProjectSkill[]>(`/api/projects/${projectId}/skills`)

export const setProjectSkill = (
  projectId: number,
  skillId: string,
  enabled: boolean,
): Promise<{ skill_id: string; enabled: boolean; always_on: boolean }> =>
  apiClient.put<{ skill_id: string; enabled: boolean; always_on: boolean }>(
    `/api/projects/${projectId}/skills/${skillId}?enabled=${enabled}`,
    undefined,
  )
