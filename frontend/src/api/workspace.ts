import { ApiError } from './client'
import type {
  WorkspaceFileResponse,
  WorkspaceFileSaveResponse,
  WorkspaceIngestResponse,
  WorkspaceTreeResponse,
} from '@/types/api'

const BASE = (projectId: number) => `/api/projects/${projectId}/workspace`

export const getWorkspaceTree = (projectId: number): Promise<WorkspaceTreeResponse> =>
  fetch(`${BASE(projectId)}/tree`).then((r) => {
    if (!r.ok) throw new ApiError(r.status, r.statusText)
    return r.json() as Promise<WorkspaceTreeResponse>
  })

export const getWorkspaceFile = (
  projectId: number,
  path: string,
): Promise<WorkspaceFileResponse> =>
  fetch(`${BASE(projectId)}/file?path=${encodeURIComponent(path)}`).then((r) => {
    if (!r.ok) throw new ApiError(r.status, r.statusText)
    return r.json() as Promise<WorkspaceFileResponse>
  })

export const putWorkspaceFile = (
  projectId: number,
  path: string,
  content: string,
): Promise<WorkspaceFileSaveResponse> =>
  fetch(`${BASE(projectId)}/file`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  }).then((r) => {
    if (!r.ok) throw new ApiError(r.status, r.statusText)
    return r.json() as Promise<WorkspaceFileSaveResponse>
  })

export const ingestWorkspaceFiles = (
  projectId: number,
  section: string,
  files: File[],
): Promise<WorkspaceIngestResponse> => {
  const form = new FormData()
  form.append('section', section)
  for (const f of files) form.append('files', f)
  return fetch(`${BASE(projectId)}/ingest`, { method: 'POST', body: form }).then((r) => {
    if (!r.ok) throw new ApiError(r.status, r.statusText)
    return r.json() as Promise<WorkspaceIngestResponse>
  })
}
