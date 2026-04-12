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
