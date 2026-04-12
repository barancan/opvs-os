import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { getSettingOrNull, testConnection, upsertSetting } from '@/api/settings'
import { ConnectionBadge } from '@/components/shared/ConnectionBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useAppStore } from '@/stores/useAppStore'

// ---------------------------------------------------------------------------
// Workspace section
// ---------------------------------------------------------------------------

function WorkspaceSection() {
  const qc = useQueryClient()
  const [value, setValue] = useState('')

  const { data } = useQuery({
    queryKey: ['setting', 'workspace_path'],
    queryFn: () => getSettingOrNull('workspace_path'),
  })

  // Sync fetched value into local state when query result arrives
  useEffect(() => {
    if (data !== undefined) {
      setValue(data?.value ?? '')
    }
  }, [data])

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
}

function SecretKeyRow({ settingKey, label, service }: SecretKeyRowProps) {
  const qc = useQueryClient()
  const [inputValue, setInputValue] = useState('')
  const connectionStatuses = useAppStore((s) => s.connectionStatuses)
  const setConnectionStatus = useAppStore((s) => s.setConnectionStatus)

  const { data: existing } = useQuery({
    queryKey: ['setting', settingKey],
    queryFn: () => getSettingOrNull(settingKey),
  })

  const keyIsSaved = existing !== undefined && existing !== null

  const saveMutation = useMutation({
    mutationFn: () => upsertSetting(settingKey, { value: inputValue, is_secret: true }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', settingKey] })
      setInputValue('')
      setConnectionStatus(service, { status: 'untested' })
      toast.success('Saved')
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const testMutation = useMutation({
    mutationFn: () => testConnection(service),
    onSuccess: (result) => {
      setConnectionStatus(service, {
        status: result.ok ? 'ok' : 'error',
        error: result.error ?? undefined,
      })
    },
    onError: (err) => {
      setConnectionStatus(service, {
        status: 'error',
        error: err instanceof Error ? err.message : String(err),
      })
    },
  })

  const connState = connectionStatuses[service] ?? { status: 'untested' as const }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor={settingKey}>{label}</Label>
        <Input
          id={settingKey}
          type="password"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Enter API key to update"
          autoComplete="new-password"
        />
        {keyIsSaved && (
          <p className="text-xs text-zinc-500">
            A key is already saved. Enter a new value to replace it.
          </p>
        )}
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
        <ConnectionBadge status={connState.status} error={connState.error} />
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
  const connectionStatuses = useAppStore((s) => s.connectionStatuses)
  const setConnectionStatus = useAppStore((s) => s.setConnectionStatus)

  const { data } = useQuery({
    queryKey: ['setting', 'ollama_host'],
    queryFn: () => getSettingOrNull('ollama_host'),
  })

  useEffect(() => {
    if (data !== undefined) {
      setValue(data?.value ?? '')
    }
  }, [data])

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
    onSuccess: (result) => {
      setConnectionStatus('ollama', {
        status: result.ok ? 'ok' : 'error',
        error: result.error ?? undefined,
      })
    },
    onError: (err) => {
      setConnectionStatus('ollama', {
        status: 'error',
        error: err instanceof Error ? err.message : String(err),
      })
    },
  })

  const connState = connectionStatuses['ollama'] ?? { status: 'untested' as const }

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
        <ConnectionBadge status={connState.status} error={connState.error} />
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
