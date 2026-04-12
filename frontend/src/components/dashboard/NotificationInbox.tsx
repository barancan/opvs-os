import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckIcon, XIcon } from 'lucide-react'
import { getNotifications, updateNotificationStatus } from '@/api/notifications'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Notification, NotificationSourceType, NotificationStatus } from '@/types/api'

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const sourceVariant: Record<
  NotificationSourceType,
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  system: 'secondary',
  orchestrator: 'default',
  agent: 'outline',
  job: 'outline',
}

interface NotificationCardProps {
  notification: Notification
  showActions: boolean
}

function NotificationCard({ notification, showActions }: NotificationCardProps) {
  const qc = useQueryClient()

  const updateMutation = useMutation({
    mutationFn: (status: NotificationStatus) =>
      updateNotificationStatus(notification.id, status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const timestamp =
    showActions
      ? relativeTime(notification.created_at)
      : notification.completed_at
        ? relativeTime(notification.completed_at)
        : relativeTime(notification.updated_at)

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium text-sm text-zinc-100 leading-tight">
          {notification.title}
        </span>
        <span className="text-xs text-zinc-500 shrink-0">{timestamp}</span>
      </div>
      <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed">
        {notification.body}
      </p>
      <div className="flex items-center justify-between">
        <Badge variant={sourceVariant[notification.source_type]}>
          {notification.source_type}
        </Badge>
        {showActions && (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs text-green-400 hover:text-green-300 hover:bg-green-950"
              onClick={() => updateMutation.mutate('completed')}
              disabled={updateMutation.isPending}
              aria-label="Mark as complete"
            >
              <CheckIcon className="h-3 w-3 mr-1" />
              Complete
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs text-zinc-400 hover:text-zinc-300 hover:bg-zinc-800"
              onClick={() => updateMutation.mutate('dismissed')}
              disabled={updateMutation.isPending}
              aria-label="Dismiss notification"
            >
              <XIcon className="h-3 w-3 mr-1" />
              Dismiss
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 gap-2 text-zinc-600">
      <CheckIcon className="h-8 w-8" />
      <p className="text-sm">{message}</p>
    </div>
  )
}

export function NotificationInbox() {
  const { data: pending = [] } = useQuery({
    queryKey: ['notifications', 'pending'],
    queryFn: () => getNotifications('pending'),
  })

  const { data: completed = [] } = useQuery({
    queryKey: ['notifications', 'completed'],
    queryFn: () => getNotifications('completed'),
  })

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-zinc-400">Notifications</h2>
      <Tabs defaultValue="inbox">
        <TabsList>
          <TabsTrigger value="inbox">
            Inbox
            {pending.length > 0 && (
              <span className="ml-1.5 rounded-full bg-red-600 px-1.5 py-0.5 text-xs text-white leading-none">
                {pending.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="completed">Completed</TabsTrigger>
        </TabsList>

        <TabsContent value="inbox" className="mt-3 space-y-2">
          {pending.length === 0 ? (
            <EmptyState message="No pending notifications" />
          ) : (
            pending.map((n) => (
              <NotificationCard key={n.id} notification={n} showActions />
            ))
          )}
        </TabsContent>

        <TabsContent value="completed" className="mt-3 space-y-2">
          {completed.length === 0 ? (
            <EmptyState message="No completed notifications yet" />
          ) : (
            completed.map((n) => (
              <NotificationCard key={n.id} notification={n} showActions={false} />
            ))
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
