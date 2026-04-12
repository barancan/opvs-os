import { useEffect, useRef } from 'react'
import type { WebSocketEvent } from '@/types/api'
import { useAppStore } from '@/stores/useAppStore'

const WS_URL = 'ws://localhost:8000/ws'
const MAX_BACKOFF_MS = 30_000

type EventHandlers = Record<string, (payload: unknown) => void>

export function useWebSocket(handlers: EventHandlers): void {
  const setWsStatus = useAppStore((s) => s.setWsStatus)
  const wsRef = useRef<WebSocket | null>(null)
  const backoffRef = useRef<number>(1_000)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handlersRef = useRef<EventHandlers>(handlers)

  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  useEffect(() => {
    let destroyed = false

    function connect() {
      if (destroyed) return
      setWsStatus('connecting')
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (destroyed) { ws.close(); return }
        backoffRef.current = 1_000
        setWsStatus('connected')
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as WebSocketEvent
          const handler = handlersRef.current[msg.type]
          if (handler) handler(msg.payload)
        } catch (e) {
          console.error('WS parse error', e)
        }
      }

      ws.onerror = () => {
        // onclose will fire next and handle reconnect
      }

      ws.onclose = () => {
        if (destroyed) return
        setWsStatus('disconnected')
        timerRef.current = setTimeout(() => {
          backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
          connect()
        }, backoffRef.current)
      }
    }

    connect()

    return () => {
      destroyed = true
      if (timerRef.current !== null) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [setWsStatus])
}
