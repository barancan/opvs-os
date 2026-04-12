import { apiClient } from './client'
import type { JobStatus, ScheduledJob, ScheduledJobCreate, ScheduledJobUpdate } from '@/types/api'

export const listJobs = (projectId?: number, status?: JobStatus) => {
  const params = new URLSearchParams()
  if (projectId !== undefined) params.set('project_id', String(projectId))
  if (status) params.set('status', status)
  const qs = params.toString()
  return apiClient.get<ScheduledJob[]>(`/api/jobs${qs ? `?${qs}` : ''}`)
}

export const createJob = (data: ScheduledJobCreate) =>
  apiClient.post<ScheduledJob>('/api/jobs', data)

export const updateJob = (id: number, data: ScheduledJobUpdate) =>
  apiClient.put<ScheduledJob>(`/api/jobs/${id}`, data)

export const deleteJob = (id: number) =>
  apiClient.delete<{ deleted: boolean }>(`/api/jobs/${id}`)

export const runJobNow = (id: number) =>
  apiClient.post<{ status: string }>(`/api/jobs/${id}/run`)
