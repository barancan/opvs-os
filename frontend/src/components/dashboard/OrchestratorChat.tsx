import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontalIcon, SendIcon, Trash2Icon } from 'lucide-react'
import { toast } from 'sonner'
import { clearChatHistory, getChatHistory, getCompactStatus, sendMessage } from '@/api/chat'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/stores/useAppStore'
import type { ChatMessage } from '@/types/api'

// ------------------------------------------------------------------
// Compact status indicator
// ------------------------------------------------------------------

function TokenUsageIndicator() {
  const { data } = useQuery({
    queryKey: ['compactStatus'],
    queryFn: getCompactStatus,
    refetchInterval: 30_000,
  })

  if (!data) return null

  const pct = data.total_tokens / data.threshold
  const colorClass =
    pct > 0.85
      ? 'text-red-400'
      : pct > 0.6
        ? 'text-amber-400'
        : 'text-zinc-500'

  return (
    <span className={cn('text-xs tabular-nums', colorClass)}>
      {data.total_tokens.toLocaleString()} / {data.threshold.toLocaleString()} tokens
    </span>
  )
}

// ------------------------------------------------------------------
// Message bubble
// ------------------------------------------------------------------

function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.is_compact_summary) {
    return (
      <div className="flex justify-center py-1">
        <span className="text-xs text-zinc-500 italic">— Context compacted —</span>
      </div>
    )
  }

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-zinc-700 px-3 py-2 text-sm text-zinc-100">
          {msg.content}
        </div>
      </div>
    )
  }

  if (msg.role === 'assistant') {
    return (
      <div className="flex gap-2 items-start">
        <div className="shrink-0 w-6 h-6 rounded-full bg-zinc-600 flex items-center justify-center text-xs text-zinc-300 font-bold">
          OS
        </div>
        <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-zinc-800 px-3 py-2 text-sm text-zinc-200 whitespace-pre-wrap">
          {msg.content}
        </div>
      </div>
    )
  }

  return null
}

// ------------------------------------------------------------------
// Streaming bubble
// ------------------------------------------------------------------

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex gap-2 items-start">
      <div className="shrink-0 w-6 h-6 rounded-full bg-zinc-600 flex items-center justify-center text-xs text-zinc-300 font-bold">
        OS
      </div>
      <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-zinc-800 px-3 py-2 text-sm text-zinc-200 whitespace-pre-wrap">
        {content}
        <span className="inline-block w-1 h-3 bg-zinc-400 animate-pulse ml-0.5 align-middle" />
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Main chat component
// ------------------------------------------------------------------

export function OrchestratorChat() {
  const qc = useQueryClient()
  const clientId = useRef(crypto.randomUUID())
  const [input, setInput] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [compactIndicators, setCompactIndicators] = useState<number[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const streamingContent = useAppStore((s) => s.streamingContent)
  const isStreaming = useAppStore((s) => s.isStreaming)
  const clearStreamingContent = useAppStore((s) => s.clearStreamingContent)
  const setIsStreaming = useAppStore((s) => s.setIsStreaming)

  const { data: history = [] } = useQuery({
    queryKey: ['chatHistory'],
    queryFn: getChatHistory,
  })

  // Listen for compact_triggered via query invalidation — track locally for indicator
  const prevHistoryLen = useRef(history.length)
  useEffect(() => {
    if (history.length < prevHistoryLen.current) {
      setCompactIndicators((prev) => [...prev, Date.now()])
    }
    prevHistoryLen.current = history.length
  }, [history.length])

  // Auto-scroll to bottom when messages change or streaming
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [history, streamingContent])

  // Close menu on outside click
  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    if (showMenu) document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [showMenu])

  const sendMutation = useMutation({
    mutationFn: (content: string) => sendMessage(content, clientId.current),
    onMutate: (content: string) => {
      // Show user message immediately without waiting for the server round-trip
      clearStreamingContent()
      setIsStreaming(true)
      const optimisticId = -Date.now()
      const optimisticMsg: ChatMessage = {
        id: optimisticId,
        role: 'user',
        content,
        token_count: 0,
        is_compact_summary: false,
        created_at: new Date().toISOString(),
      }
      qc.setQueryData<ChatMessage[]>(['chatHistory'], (old = []) => [...old, optimisticMsg])
      return { optimisticId }
    },
    onSuccess: () => {
      // The WS chat_complete handler already does this when WS is working.
      // Calling again here is idempotent and covers the WS-broken fallback.
      setIsStreaming(false)
      clearStreamingContent()
      void qc.invalidateQueries({ queryKey: ['chatHistory'] })
    },
    onError: (err, _content, context) => {
      if (context) {
        qc.setQueryData<ChatMessage[]>(['chatHistory'], (old = []) =>
          old.filter((m) => m.id !== context.optimisticId),
        )
      }
      setIsStreaming(false)
      clearStreamingContent()
      toast.error(`Send failed: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  const clearMutation = useMutation({
    mutationFn: clearChatHistory,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['chatHistory'] })
      void qc.invalidateQueries({ queryKey: ['compactStatus'] })
      toast.success('Chat history cleared')
      setShowMenu(false)
    },
    onError: (err) => {
      toast.error(`Clear failed: ${err instanceof Error ? err.message : String(err)}`)
    },
  })

  function handleSend() {
    const trimmed = input.trim()
    if (!trimmed) return

    if (trimmed === '/compact') {
      clearMutation.mutate()
      setInput('')
      return
    }

    sendMutation.mutate(trimmed)
    setInput('')
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-96 rounded-lg border border-zinc-800 bg-zinc-950">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-medium text-zinc-400">Orchestrator</span>
        <div className="flex items-center gap-3">
          <TokenUsageIndicator />
          {/* Menu */}
          <div className="relative" ref={menuRef}>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0"
              onClick={() => setShowMenu((v) => !v)}
              aria-label="Chat options"
            >
              <MoreHorizontalIcon className="h-4 w-4" />
            </Button>
            {showMenu && (
              <div className="absolute right-0 top-7 z-50 w-40 rounded-md border border-zinc-700 bg-zinc-900 shadow-lg py-1">
                <button
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
                  onClick={() => clearMutation.mutate()}
                  disabled={clearMutation.isPending}
                >
                  <Trash2Icon className="h-3 w-3" />
                  Clear history
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0"
      >
        {history.length === 0 && !isStreaming && (
          <div className="flex items-center justify-center h-full">
            <p className="text-xs text-zinc-600">
              Ask the orchestrator anything about your projects…
            </p>
          </div>
        )}

        {history.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {compactIndicators.map((ts) => (
          <div key={ts} className="flex justify-center py-1">
            <span className="text-xs text-zinc-500 italic">— Context compacted —</span>
          </div>
        ))}

        {isStreaming && <StreamingBubble content={streamingContent} />}
      </div>

      {/* Input area */}
      <div className="flex gap-2 px-3 py-2 border-t border-zinc-800 shrink-0">
        <label htmlFor="chat-input" className="sr-only">
          Message the orchestrator
        </label>
        <input
          id="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the orchestrator… (or /compact to clear)"
          disabled={sendMutation.isPending || isStreaming}
          className={cn(
            'flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100',
            'placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          )}
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={sendMutation.isPending || isStreaming || !input.trim()}
          aria-label="Send message"
        >
          <SendIcon className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
