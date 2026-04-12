import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { getSetting, testConnection, upsertSetting } from '@/api/settings'
import { ConnectionBadge } from '@/components/shared/ConnectionBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import type { ConnectionTestResult } from '@/types/api'
import { ApiError } from '@/api/client'

// ---------------------------------------------------------------------------
// Workspace section
// ---------------------------------------------------------------------------

function WorkspaceSection() {
  const qc = useQueryClient()
  const [value, setValue] = useState('')

  const { data } = useQuery({
    queryKey: ['setting', 'workspace_path'],
    queryFn: () => getSetting('workspace_path'),
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false
      return failureCount < 1
    },
    select: (d) => d.value,
  })

  // Sync fetched value into local state once
  const [synced, setSynced] = useState(false)
  if (data !== undefined && !synced) {
    setValue(data)
    setSynced(true)
  }

  const mutation = useMutation({
    mutationFn: () => upsertSetting('workspace_path', { value, is_secret: false }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', 'workspace_path'] })
      toast.success('Saved')
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Workspace</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="workspace_path">Workspace path</Label>
          <Input
            id="workspace_path"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="./workspace"
          />
          <p className="text-xs text-muted-foreground">
            Agents can only read and write files within this directory
          </p>
        </div>
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save
        </Button>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Reusable secret key row
// ---------------------------------------------------------------------------

interface SecretKeyRowProps {
  settingKey: string
  label: string
  service: string
  placeholder?: string
}

function SecretKeyRow({ settingKey, label, service, placeholder }: SecretKeyRowProps) {
  const qc = useQueryClient()
  const [inputValue, setInputValue] = useState('')
  const [connResult, setConnResult] = useState<ConnectionTestResult | null>(null)

  // Check if key exists (to show placeholder hint)
  const { data: existing } = useQuery({
    queryKey: ['setting', settingKey],
    queryFn: () => getSetting(settingKey),
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false
      return failureCount < 1
    },
  })

  const saveMutation = useMutation({
    mutationFn: () => upsertSetting(settingKey, { value: inputValue, is_secret: true }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', settingKey] })
      setInputValue('')
      setConnResult(null)
      toast.success('Saved')
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const testMutation = useMutation({
    mutationFn: () => testConnection(service),
    onSuccess: (result) => {
      setConnResult(result)
    },
    onError: (err) => {
      setConnResult({ ok: false, error: err instanceof Error ? err.message : String(err) })
    },
  })

  const badgeStatus = connResult === null ? 'untested' : connResult.ok ? 'ok' : 'error'

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor={settingKey}>{label}</Label>
        <Input
          id={settingKey}
          type="password"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder={
            existing ? 'API key saved — enter new value to update' : (placeholder ?? 'Enter API key')
          }
          autoComplete="new-password"
        />
      </div>
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || !inputValue}
        >
          {saveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Test Connection
        </Button>
        <ConnectionBadge
          status={badgeStatus}
          error={connResult?.error}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ollama section (non-secret host input)
// ---------------------------------------------------------------------------

function OllamaRow() {
  const qc = useQueryClient()
  const [value, setValue] = useState('')
  const [connResult, setConnResult] = useState<ConnectionTestResult | null>(null)

  const { data } = useQuery({
    queryKey: ['setting', 'ollama_host'],
    queryFn: () => getSetting('ollama_host'),
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false
      return failureCount < 1
    },
    select: (d) => d.value,
  })

  const [synced, setSynced] = useState(false)
  if (data !== undefined && !synced) {
    setValue(data)
    setSynced(true)
  }

  const saveMutation = useMutation({
    mutationFn: () => upsertSetting('ollama_host', { value, is_secret: false }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', 'ollama_host'] })
      toast.success('Saved')
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const testMutation = useMutation({
    mutationFn: () => testConnection('ollama'),
    onSuccess: (result) => setConnResult(result),
    onError: (err) => {
      setConnResult({ ok: false, error: err instanceof Error ? err.message : String(err) })
    },
  })

  const badgeStatus = connResult === null ? 'untested' : connResult.ok ? 'ok' : 'error'

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor="ollama_host">Ollama host</Label>
        <Input
          id="ollama_host"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="http://localhost:11434"
        />
      </div>
      <div className="flex items-center gap-3">
        <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          {saveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Test Connection
        </Button>
        <ConnectionBadge status={badgeStatus} error={connResult?.error} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Settings page
// ---------------------------------------------------------------------------

export default function Settings() {
  return (
    <div className="p-8 space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold text-zinc-100">Settings</h1>

      <WorkspaceSection />

      <Card>
        <CardHeader>
          <CardTitle>AI Models</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <h3 className="text-sm font-medium text-zinc-300 mb-3">Anthropic</h3>
            <SecretKeyRow
              settingKey="anthropic_api_key"
              label="API Key"
              service="anthropic"
              placeholder="sk-ant-..."
            />
          </div>
          <Separator />
          <div>
            <h3 className="text-sm font-medium text-zinc-300 mb-3">Ollama</h3>
            <OllamaRow />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Linear</CardTitle>
        </CardHeader>
        <CardContent>
          <SecretKeyRow
            settingKey="linear_api_key"
            label="API Key"
            service="linear"
            placeholder="lin_api_..."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>MCP Connections</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            MCP server connections will be configurable here in a future update.
          </p>
        </CardContent>
      </Card>

      <Card className="border-red-200">
        <CardHeader>
          <CardTitle className="text-red-500">Danger Zone</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Kill-switch and recovery tools will appear here.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
