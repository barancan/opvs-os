import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getChatroomMessages, postChatroomReply } from '@/api/sessions'
import { useAppStore } from '@/stores/useAppStore'
import type { AgentMessage } from '@/types/api'

// ── ChatroomMessage sub-component ────────────────────────────────────────────

interface ChatroomMessageProps {
  message: AgentMessage
  onReply: (id: number) => void
  isReplying: boolean
  replyInput: string
  onReplyInputChange: (val: string) => void
  onReplySend: () => void
}

function ChatroomMessage({
  message,
  onReply,
  isReplying,
  replyInput,
  onReplyInputChange,
  onReplySend,
}: ChatroomMessageProps) {
  const isAgent = message.sender_type === 'agent'
  const isUser = message.sender_type === 'user'
  const isSystem = message.sender_type === 'system'
  const needsResponse = message.requires_response && !message.response_provided

  return (
    <div
      className={`text-xs rounded-lg p-2 ${
        isUser
          ? 'bg-zinc-800 ml-4'
          : isAgent
            ? 'bg-zinc-900 border border-zinc-700'
            : 'text-zinc-500 italic text-center'
      }`}
    >
      {!isSystem && (
        <div
          className={`font-medium mb-1 ${
            isAgent ? (needsResponse ? 'text-amber-400' : 'text-blue-400') : 'text-zinc-400'
          }`}
        >
          {message.sender_name}
          {needsResponse && (
            <span className="ml-2 text-amber-400 animate-pulse">● waiting</span>
          )}
        </div>
      )}

      <div className="text-zinc-300 whitespace-pre-wrap break-words">{message.content}</div>

      {needsResponse && (
        <button
          onClick={() => onReply(message.id)}
          className="mt-2 text-xs text-amber-400 hover:text-amber-300 underline"
        >
          Reply
        </button>
      )}

      {message.reply_to_id && (
        <div className="text-zinc-600 mt-1">↩ reply</div>
      )}

      {isReplying && (
        <div className="mt-2 flex gap-1">
          <input
            autoFocus
            className="flex-1 text-xs bg-zinc-800 border border-zinc-600 rounded px-2 py-1
                       text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-amber-500"
            placeholder="Type your reply…"
            value={replyInput}
            onChange={(e) => onReplyInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onReplySend() }
              if (e.key === 'Escape') onReply(0)
            }}
          />
          <button
            onClick={onReplySend}
            className="text-xs text-amber-400 hover:text-amber-300 px-1"
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}

// ── ChatroomPanel ─────────────────────────────────────────────────────────────

export function ChatroomPanel() {
  const activeProjectId = useAppStore((s) => s.activeProjectId)
  const chatroomMessages = useAppStore((s) => s.chatroomMessages)
  const addChatroomMessage = useAppStore((s) => s.addChatroomMessage)
  const activeSessions = useAppStore((s) => s.activeSessions)

  const [input, setInput] = useState('')
  const [replyingToId, setReplyingToId] = useState<number | null>(null)
  const [replyInput, setReplyInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load history from API
  const { data: history } = useQuery({
    queryKey: ['chatroomMessages', activeProjectId],
    queryFn: () => getChatroomMessages(activeProjectId!),
    enabled: activeProjectId !== null,
    staleTime: 0,
  })

  // Seed store from query once on load (don't overwrite live messages)
  useEffect(() => {
    if (history && chatroomMessages.length === 0) {
      history.forEach(addChatroomMessage)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history])

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatroomMessages.length])

  // Filter to active project
  const messages = chatroomMessages.filter(
    (m) => activeProjectId === null || m.project_id === activeProjectId,
  )

  // Count active agents from running sessions
  const activeAgentCount = activeSessions.filter((s) =>
    ['queued', 'running', 'waiting'].includes(s.status),
  ).length

  async function handleSend() {
    if (!input.trim() || activeProjectId === null || sending) return
    setSending(true)
    try {
      const msg = await postChatroomReply(activeProjectId, input.trim())
      addChatroomMessage(msg)
      setInput('')
    } catch {
      toast.error('Failed to send message')
    } finally {
      setSending(false)
    }
  }

  function handleReplyClick(id: number) {
    setReplyingToId((prev) => (prev === id ? null : id))
    setReplyInput('')
  }

  async function handleReplySend() {
    if (!replyInput.trim() || activeProjectId === null || replyingToId === null || sending) return
    const targetMsg = messages.find((m) => m.id === replyingToId)
    setSending(true)
    try {
      const msg = await postChatroomReply(
        activeProjectId,
        replyInput.trim(),
        replyingToId,
        targetMsg?.session_uuid ?? undefined,
      )
      addChatroomMessage(msg)
      setReplyingToId(null)
      setReplyInput('')
    } catch {
      toast.error('Failed to send reply')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full w-[280px] flex-shrink-0 border-l border-zinc-800 bg-zinc-950">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between flex-shrink-0">
        <span className="text-sm font-medium text-zinc-300">Agent Chat</span>
        <span className="text-xs text-zinc-500">{activeAgentCount} active</span>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2 min-h-0">
        {messages.length === 0 ? (
          <p className="text-xs text-zinc-600 text-center mt-8">
            No messages yet. Agents will appear here when active.
          </p>
        ) : (
          messages.map((msg) => (
            <ChatroomMessage
              key={msg.id}
              message={msg}
              onReply={handleReplyClick}
              isReplying={replyingToId === msg.id}
              replyInput={replyInput}
              onReplyInputChange={setReplyInput}
              onReplySend={() => void handleReplySend()}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-zinc-800 flex-shrink-0">
        <div className="flex gap-2">
          <input
            className="flex-1 text-sm bg-zinc-900 border border-zinc-700 rounded px-2 py-1.5
                       text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
            placeholder="Message all agents…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend() }
            }}
          />
          <button
            onClick={() => void handleSend()}
            disabled={sending}
            className="text-xs text-zinc-400 hover:text-zinc-200 px-2 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
