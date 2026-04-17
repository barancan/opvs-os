export interface Setting {
  id: number
  key: string
  value: string
  is_secret: boolean
  created_at: string
  updated_at: string
}

export interface SettingUpdate {
  value: string
  is_secret?: boolean
}

export interface ConnectionTestResult {
  ok: boolean
  error?: string
}

export interface WebSocketEvent<T = unknown> {
  type: string
  payload: T
  ts: string
}

export interface HealthResponse {
  status: string
  version: string
}

// Notifications
export type NotificationStatus = 'pending' | 'completed' | 'dismissed'
export type NotificationSourceType = 'orchestrator' | 'agent' | 'job' | 'system'

export interface Notification {
  id: number
  title: string
  body: string
  status: NotificationStatus
  source_type: NotificationSourceType
  agent_id: string | null
  session_id: string | null
  job_id: string | null
  priority: number
  orchestrator_prioritised: boolean
  created_at: string
  updated_at: string
  completed_at: string | null
}

export type MessageRole = 'user' | 'assistant' | 'system'

export interface ChatMessage {
  id: number
  role: MessageRole
  content: string
  token_count: number
  is_compact_summary: boolean
  created_at: string
}

export interface ChatRequest {
  content: string
}

export interface CompactStatus {
  total_tokens: number
  threshold: number
  compacted: boolean
}

export interface KillSwitchStatus {
  active: boolean
  activated_at: string | null
}

// Projects
export type ProjectStatus = 'active' | 'archived'

export interface LinearLink {
  id: number
  project_id: number
  linear_project_id: string
  linear_project_name: string
  created_at: string
}

export interface Project {
  id: number
  name: string
  slug: string
  description: string | null
  status: ProjectStatus
  created_at: string
  updated_at: string
  linear_links: LinearLink[]
}

export interface ProjectCreate {
  name: string
  description?: string
}

export interface ProjectUpdate {
  name?: string
  description?: string
  status?: ProjectStatus
}

export interface LinearLinkCreate {
  linear_project_id: string
  linear_project_name: string
}

// Tool approvals
export interface ToolApprovalRequest {
  request_id: string
  tool_name: string
  platform: string
  action: string
  description: string
  parameters: Record<string, unknown>
}

export type ToolApprovalStatus = 'pending' | 'approved' | 'rejected' | 'executing' | 'done' | 'failed'

export interface ToolApprovalState extends ToolApprovalRequest {
  status: ToolApprovalStatus
  result?: string
}

// Scheduled Jobs
export type JobStatus = 'active' | 'paused' | 'archived'

export interface ScheduledJob {
  id: number
  project_id: number
  name: string
  description: string | null
  cron: string
  timezone: string
  prompt: string
  status: JobStatus
  last_run_at: string | null
  last_run_status: string | null
  created_at: string
  updated_at: string
}

export interface ScheduledJobCreate {
  project_id: number
  name: string
  description?: string
  cron: string
  timezone: string
  prompt: string
}

export interface ScheduledJobUpdate {
  name?: string
  description?: string
  cron?: string
  timezone?: string
  prompt?: string
  status?: JobStatus
}

// Personas
export interface Persona {
  id: number
  name: string
  description: string | null
  model: string
  instructions: string
  enabled_skills: string[]
  temperature: number
  max_tokens: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface PersonaCreate {
  name: string
  description?: string
  model?: string
  instructions?: string
  enabled_skills?: string[]
  temperature?: number
  max_tokens?: number
}

export interface PersonaUpdate {
  name?: string
  description?: string
  model?: string
  instructions?: string
  enabled_skills?: string[]
  temperature?: number
  max_tokens?: number
  is_active?: boolean
}

// Agent Sessions
export type SessionStatus = 'queued' | 'running' | 'waiting' | 'completed' | 'failed' | 'halted'

export interface AgentSession {
  id: number
  session_uuid: string
  project_id: number
  persona_id: number
  persona_name: string
  task: string
  status: SessionStatus
  model_snapshot: string
  total_tokens: number
  result_summary: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

// Chatroom
export type SenderType = 'user' | 'agent' | 'orchestrator' | 'system' | 'event'

export interface AgentMessage {
  id: number
  project_id: number
  session_uuid: string | null
  sender_type: SenderType
  sender_name: string
  content: string
  requires_response: boolean
  response_provided: boolean
  reply_to_id: number | null
  created_at: string
}

// Skills
export interface ProjectSkill {
  skill_id: string
  display_name: string
  enabled: boolean
  always_on: boolean
  requires_setting: string | null
  setting_configured: boolean
}
