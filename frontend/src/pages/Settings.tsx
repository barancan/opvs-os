import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { activateKillSwitch, getKillSwitchStatus, recoverKillSwitch } from '@/api/killswitch'
import { getSettingOrNull, testConnection, upsertSetting } from '@/api/settings'
import { ConnectionBadge } from '@/components/shared/ConnectionBadge'
import { SystemPromptModal } from '@/components/settings/SystemPromptModal'
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
  const [isEditing, setIsEditing] = useState(false)
  const connectionStatuses = useAppStore((s) => s.connectionStatuses)
  const setConnectionStatus = useAppStore((s) => s.setConnectionStatus)

  const { data: existing } = useQuery({
    queryKey: ['setting', settingKey],
    queryFn: () => getSettingOrNull(settingKey),
  })

  const keyIsSaved = existing !== undefined && existing !== null

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

  const saveMutation = useMutation({
    mutationFn: () => upsertSetting(settingKey, { value: inputValue, is_secret: true }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', settingKey] })
      setInputValue('')
      setIsEditing(false)
      setConnectionStatus(service, { status: 'untested' })
      toast.success('Saved')
      testMutation.mutate()
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const connState = connectionStatuses[service] ?? { status: 'untested' as const }

  const SAVED_MASK = '••••••••••••••••'
  const displayValue = keyIsSaved && !isEditing ? SAVED_MASK : inputValue

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor={settingKey}>{label}</Label>
        <Input
          id={settingKey}
          type="password"
          value={displayValue}
          onFocus={() => {
            if (keyIsSaved && !isEditing) {
              setIsEditing(true)
              setInputValue('')
            }
          }}
          onBlur={() => {
            if (!inputValue) setIsEditing(false)
          }}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Enter API key"
          autoComplete="new-password"
        />
      </div>
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || !isEditing || !inputValue}
        >
          {saveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending || saveMutation.isPending}
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
// Orchestrator model section
// ---------------------------------------------------------------------------

function OrchestratorSection() {
  const qc = useQueryClient()
  const [modelValue, setModelValue] = useState('')
  const [contextWindow, setContextWindow] = useState('8192')
  const [promptModalOpen, setPromptModalOpen] = useState(false)

  const { data: modelData } = useQuery({
    queryKey: ['setting', 'orchestrator_model'],
    queryFn: () => getSettingOrNull('orchestrator_model'),
  })

  const { data: contextWindowData } = useQuery({
    queryKey: ['setting', 'ollama_context_window'],
    queryFn: () => getSettingOrNull('ollama_context_window'),
  })

  useEffect(() => {
    if (modelData !== undefined) {
      setModelValue(modelData?.value ?? '')
    }
  }, [modelData])

  useEffect(() => {
    if (contextWindowData !== undefined) {
      setContextWindow(contextWindowData?.value ?? '8192')
    }
  }, [contextWindowData])

  const modelMutation = useMutation({
    mutationFn: () =>
      upsertSetting('orchestrator_model', { value: modelValue, is_secret: false }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', 'orchestrator_model'] })
      toast.success('Saved')
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const contextWindowMutation = useMutation({
    mutationFn: () =>
      upsertSetting('ollama_context_window', { value: contextWindow, is_secret: false }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setting', 'ollama_context_window'] })
      toast.success('Saved')
    },
    onError: (err) => {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Orchestrator</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">

        {/* Model name */}
        <div className="flex flex-col gap-2">
          <Label htmlFor="orchestrator_model">Model</Label>
          <div className="flex gap-2">
            <Input
              id="orchestrator_model"
              value={modelValue}
              onChange={(e) => setModelValue(e.target.value)}
              placeholder="claude-sonnet-4-6"
              className="flex-1"
            />
            <Button
              variant="outline"
              onClick={() => modelMutation.mutate()}
              disabled={modelMutation.isPending}
            >
              {modelMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </div>
          <p className="text-xs text-zinc-500">
            Default: claude-sonnet-4-6. Use any Anthropic model ID or an Ollama model name
            (e.g. gemma3:4b). Ollama models route to your local Ollama instance.
          </p>
        </div>

        {/* Ollama context window */}
        <div className="flex flex-col gap-2">
          <Label htmlFor="ollama-context-window">Ollama context window (tokens)</Label>
          <div className="flex gap-2">
            <Input
              id="ollama-context-window"
              type="number"
              min={1024}
              max={131072}
              step={1024}
              value={contextWindow}
              onChange={(e) => setContextWindow(e.target.value)}
              className="w-40"
            />
            <Button
              variant="outline"
              onClick={() => contextWindowMutation.mutate()}
              disabled={contextWindowMutation.isPending}
            >
              {contextWindowMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Save
            </Button>
          </div>
          <p className="text-xs text-zinc-500">
            Context window size for local Ollama models. Compaction triggers at 75% of this
            value. Default: 8192.
          </p>
        </div>

        {/* System prompt */}
        <div className="flex flex-col gap-2">
          <Label>System prompt</Label>
          <p className="text-xs text-zinc-500">
            The static instructions sent to the orchestrator. Dynamic context (memory, project
            state, notifications) is always appended automatically.
          </p>
          <div>
            <Button variant="outline" onClick={() => setPromptModalOpen(true)}>
              Edit system prompt
            </Button>
          </div>
        </div>

      </CardContent>

      <SystemPromptModal
        open={promptModalOpen}
        onClose={() => setPromptModalOpen(false)}
      />
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Danger Zone section
// ---------------------------------------------------------------------------

function DangerZoneSection() {
  const qc = useQueryClient()
  const [armed, setArmed] = useState(false)
  const [recoveryReason, setRecoveryReason] = useState('')

  const { data: ksData } = useQuery({
    queryKey: ['killswitch'],
    queryFn: getKillSwitchStatus,
    refetchInterval: 10_000,
  })

  const isActive = ksData?.active ?? false

  const activateMutation = useMutation({
    mutationFn: activateKillSwitch,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['killswitch'] })
      setArmed(false)
      toast.success('Kill switch activated')
    },
    onError: (err) => {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const recoverMutation = useMutation({
    mutationFn: () => recoverKillSwitch(recoveryReason),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['killswitch'] })
      setRecoveryReason('')
      toast.success('System recovered. Check workspace/_memory/inbox/ for the recovery log.')
    },
    onError: (err) => {
      toast.error(`Failed: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  function handleActivateClick() {
    if (!armed) {
      setArmed(true)
      setTimeout(() => setArmed(false), 5000)
    } else {
      activateMutation.mutate()
    }
  }

  const canRecover = recoveryReason.trim().length >= 10

  return (
    <Card className={isActive ? 'border-red-600' : 'border-red-200'}>
      <CardHeader>
        <CardTitle className="text-red-500">Danger Zone</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isActive ? (
          <div className="space-y-4">
            <div className="flex items-start gap-2 text-amber-400">
              <span className="text-base">⚠</span>
              <div>
                <p className="text-sm font-medium">Kill switch is active</p>
                {ksData?.activated_at && (
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Activated at:{' '}
                    {new Date(ksData.activated_at).toLocaleString()}
                  </p>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="recovery_reason">Recovery reason</Label>
              <textarea
                id="recovery_reason"
                value={recoveryReason}
                onChange={(e) => setRecoveryReason(e.target.value)}
                placeholder="Describe why you are recovering the system (min 10 characters)…"
                rows={3}
                className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500 resize-none"
              />
              <p className="text-xs text-zinc-500">
                {recoveryReason.trim().length} / 10 characters minimum
              </p>
            </div>
            <Button
              variant="destructive"
              onClick={() => recoverMutation.mutate()}
              disabled={recoverMutation.isPending || !canRecover}
            >
              {recoverMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Recover System
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Kill switch is inactive. The system is operating normally.
            </p>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                className="border-red-600 text-red-400 hover:bg-red-950 hover:text-red-300"
                onClick={handleActivateClick}
                disabled={activateMutation.isPending}
              >
                {activateMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                {armed ? 'Click again to confirm' : 'Activate Kill Switch'}
              </Button>
              {armed && (
                <span className="text-xs text-amber-400 animate-pulse">
                  Click again within 5s to confirm
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Main Settings page
// ---------------------------------------------------------------------------

export default function Settings() {
  return (
    <div className="p-8 space-y-6 max-w-2xl overflow-y-auto h-full">
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

      <OrchestratorSection />

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

      <DangerZoneSection />
    </div>
  )
}
