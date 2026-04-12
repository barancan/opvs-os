import { useState } from 'react'
import { Badge } from '@/components/ui/badge'

interface ConnectionBadgeProps {
  status: 'untested' | 'ok' | 'error'
  error?: string
}

export function ConnectionBadge({ status, error }: ConnectionBadgeProps) {
  const [expanded, setExpanded] = useState(false)

  if (status === 'ok') {
    return (
      <Badge className="bg-green-600 text-white hover:bg-green-600">
        Connected
      </Badge>
    )
  }

  if (status === 'error') {
    const displayError = error ?? 'Unknown error'
    const truncated = displayError.length > 60 ? displayError.slice(0, 60) + '…' : displayError
    return (
      <div className="flex flex-col gap-1">
        <Badge
          variant="destructive"
          className="cursor-pointer"
          onClick={() => setExpanded((v) => !v)}
        >
          {truncated}
        </Badge>
        {expanded && displayError.length > 60 && (
          <p className="text-xs text-red-400 break-all max-w-xs">{displayError}</p>
        )}
      </div>
    )
  }

  return (
    <Badge variant="secondary" className="text-zinc-400">
      Not tested
    </Badge>
  )
}
