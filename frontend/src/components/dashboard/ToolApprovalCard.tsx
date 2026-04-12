import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Check, ChevronDown, ChevronUp, X } from 'lucide-react'
import { approveToolAction, rejectToolAction } from '@/api/chat'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/useAppStore'
import type { ToolApprovalState } from '@/types/api'

interface ToolApprovalCardProps {
  approval: ToolApprovalState
}

export function ToolApprovalCard({ approval }: ToolApprovalCardProps) {
  const [showDetails, setShowDetails] = useState(false)
  const updateToolApproval = useAppStore((s) => s.updateToolApproval)

  const approveMutation = useMutation({
    mutationFn: () => approveToolAction(approval.request_id),
    onMutate: () => {
      updateToolApproval(approval.request_id, { status: 'executing' })
    },
    onError: () => {
      updateToolApproval(approval.request_id, { status: 'pending' })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () => rejectToolAction(approval.request_id),
    onSuccess: () => {
      updateToolApproval(approval.request_id, { status: 'rejected' })
    },
  })

  const isPending = approval.status === 'pending'
  const isExecuting = approval.status === 'executing'
  const isDone = approval.status === 'done'
  const isFailed = approval.status === 'failed'
  const isRejected = approval.status === 'rejected'

  const borderClass = isDone
    ? 'border-green-700/40 bg-green-950/20'
    : isFailed
      ? 'border-red-700/40 bg-red-950/20'
      : isPending || isExecuting
        ? 'border-amber-600/40 bg-amber-950/20'
        : 'border-zinc-700 bg-zinc-900/40'

  return (
    <div className={`rounded-lg border p-3 my-2 text-sm ${borderClass}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {approval.platform}
          </Badge>
          <span className="font-medium text-zinc-200">{approval.action}</span>
        </div>

        <div className="flex items-center gap-2">
          {isExecuting && (
            <span className="text-xs text-amber-400 animate-pulse">Executing...</span>
          )}
          {isDone && (
            <span className="text-xs text-green-400 flex items-center gap-1">
              <Check className="w-3 h-3" /> Done
            </span>
          )}
          {isFailed && (
            <span className="text-xs text-red-400 flex items-center gap-1">
              <X className="w-3 h-3" /> Failed
            </span>
          )}
          {isRejected && (
            <span className="text-xs text-zinc-500 flex items-center gap-1">
              <X className="w-3 h-3" /> Rejected
            </span>
          )}

          <button
            onClick={() => setShowDetails((v) => !v)}
            className="text-zinc-500 hover:text-zinc-300"
            aria-label={showDetails ? 'Hide details' : 'Show details'}
          >
            {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* Description */}
      <p className="text-zinc-300 text-xs mb-2">{approval.description}</p>

      {/* Result (after completion) */}
      {(isDone || isFailed) && approval.result && (
        <p className={`text-xs mb-2 ${isDone ? 'text-green-400' : 'text-red-400'}`}>
          {approval.result}
        </p>
      )}

      {/* Expanded parameters */}
      {showDetails && (
        <pre className="text-xs text-zinc-500 bg-zinc-950 rounded p-2 mb-2 overflow-x-auto">
          {JSON.stringify(approval.parameters, null, 2)}
        </pre>
      )}

      {/* Action buttons — only shown when pending */}
      {isPending && (
        <div className="flex gap-2">
          <Button
            size="sm"
            className="h-7 text-xs bg-green-700 hover:bg-green-600"
            onClick={() => approveMutation.mutate()}
            disabled={approveMutation.isPending}
          >
            <Check className="w-3 h-3 mr-1" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs border-zinc-600"
            onClick={() => rejectMutation.mutate()}
            disabled={rejectMutation.isPending}
          >
            <X className="w-3 h-3 mr-1" />
            Reject
          </Button>
        </div>
      )}
    </div>
  )
}
