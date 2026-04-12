import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { getSettingOrNull, upsertSetting } from '@/api/settings'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ANTHROPIC_PREAMBLE_DEFAULT, OLLAMA_PREAMBLE_DEFAULT } from '@/lib/orchestratorDefaults'

interface SystemPromptModalProps {
  open: boolean
  onClose: () => void
}

type Provider = 'anthropic' | 'ollama'

export function SystemPromptModal({ open, onClose }: SystemPromptModalProps) {
  const [anthropicValue, setAnthropicValue] = useState('')
  const [ollamaValue, setOllamaValue] = useState('')
  const [activeTab, setActiveTab] = useState<Provider>('anthropic')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    void Promise.all([
      getSettingOrNull('orchestrator_preamble_anthropic'),
      getSettingOrNull('orchestrator_preamble_ollama'),
    ]).then(([anthropic, ollama]) => {
      setAnthropicValue(anthropic?.value ?? '')
      setOllamaValue(ollama?.value ?? '')
    })
  }, [open])

  const handleSave = async () => {
    setSaving(true)
    try {
      const key =
        activeTab === 'anthropic'
          ? 'orchestrator_preamble_anthropic'
          : 'orchestrator_preamble_ollama'
      const value = activeTab === 'anthropic' ? anthropicValue : ollamaValue
      await upsertSetting(key, { value, is_secret: false })
      toast.success(`${activeTab === 'anthropic' ? 'Anthropic' : 'Ollama'} prompt saved`)
    } catch (err) {
      toast.error(`Failed to save: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setSaving(true)
    try {
      const key =
        activeTab === 'anthropic'
          ? 'orchestrator_preamble_anthropic'
          : 'orchestrator_preamble_ollama'
      await upsertSetting(key, { value: '', is_secret: false })
      if (activeTab === 'anthropic') {
        setAnthropicValue('')
      } else {
        setOllamaValue('')
      }
      toast.success('Reset to default')
    } catch (err) {
      toast.error(`Failed to reset: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  const tabDescription =
    activeTab === 'anthropic'
      ? 'Used when orchestrator model starts with "claude-".'
      : 'Used when orchestrator model is an Ollama model (e.g. gemma3:4b).'

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose()
      }}
    >
      <DialogContent className="max-w-3xl flex flex-col" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Edit System Prompt</DialogTitle>
          <DialogDescription>
            The static instructions given to the orchestrator before dynamic context is appended.
            Switch tabs to edit both provider variants.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={(v) => {
            setActiveTab(v as Provider)
          }}
          className="flex flex-col min-h-0"
        >
          <TabsList className="w-fit">
            <TabsTrigger value="anthropic">Anthropic</TabsTrigger>
            <TabsTrigger value="ollama">Ollama / Local</TabsTrigger>
          </TabsList>

          <TabsContent value="anthropic" className="flex flex-col gap-3 mt-3">
            <PromptTabBody
              description={tabDescription}
              value={anthropicValue}
              onChange={setAnthropicValue}
              placeholder={ANTHROPIC_PREAMBLE_DEFAULT}
            />
          </TabsContent>

          <TabsContent value="ollama" className="flex flex-col gap-3 mt-3">
            <PromptTabBody
              description={tabDescription}
              value={ollamaValue}
              onChange={setOllamaValue}
              placeholder={OLLAMA_PREAMBLE_DEFAULT}
            />
          </TabsContent>
        </Tabs>

        <DialogFooter className="mt-4 flex items-center justify-between">
          <button
            onClick={() => void handleReset()}
            disabled={saving}
            className="text-sm text-zinc-500 hover:text-zinc-300 underline disabled:opacity-50"
          >
            Reset to default
          </button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={() => void handleSave()} disabled={saving}>
              Save
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface PromptTabBodyProps {
  description: string
  value: string
  onChange: (value: string) => void
  placeholder: string
}

function PromptTabBody({ description, value, onChange, placeholder }: PromptTabBodyProps) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-zinc-500">{description}</p>
      <p className="text-xs text-zinc-500">
        Leave empty to use the built-in default. The dynamic state section (memory, project
        context, system status) is always appended automatically.
      </p>
      <textarea
        className="w-full h-96 rounded-md border border-zinc-700 bg-zinc-900 text-zinc-100 text-sm font-mono p-3 resize-y focus:outline-none focus:ring-1 focus:ring-zinc-500"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
      />
    </div>
  )
}
