/**
 * useLiveSession — React hook for the simulated-live WebSocket feed.
 *
 * Connects to /ws/live/{slug}, receives RaceState snapshots, and calls
 * onSnapshot on each message.  Shows a SIMULATED LIVE badge whenever
 * mode === 'simulated'.
 *
 * Reconnect logic: exponential backoff (1s, 2s, 4s … max 30s) with
 * visible status indicator.  Connection is closed on unmount.
 *
 * The caller must display the badge string from the snapshot whenever it
 * is non-null.
 */
import { useEffect, useRef, useState } from 'react'

export type LiveStatus = 'connecting' | 'connected' | 'reconnecting' | 'closed' | 'error'

interface LiveSnapshot {
  type: 'snapshot' | 'end' | 'error'
  session_slug: string
  session_time_seconds?: number
  mode?: 'simulated' | 'real'
  badge?: string | null
  state?: Record<string, unknown>
  detail?: string
}

interface UseLiveSessionOptions {
  sessionSlug: string
  speed?: number
  startAt?: number
  onSnapshot: (snapshot: LiveSnapshot) => void
  enabled?: boolean
}

export function useLiveSession({
  sessionSlug,
  speed = 1.0,
  startAt = 0,
  onSnapshot,
  enabled = true,
}: UseLiveSessionOptions) {
  const [status, setStatus] = useState<LiveStatus>('closed')
  const [badge, setBadge] = useState<string | null>(null)
  const [subscriberCount, setSubscriberCount] = useState<number | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelay = useRef(1000)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, [])

  function disconnect() {
    if (retryRef.current) clearTimeout(retryRef.current)
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.onmessage = null
      wsRef.current.close()
      wsRef.current = null
    }
  }

  useEffect(() => {
    if (!enabled) {
      disconnect()
      setStatus('closed')
      return
    }

    let isCurrent = true
    retryDelay.current = 1000

    function connect() {
      if (!isCurrent || !mountedRef.current) return
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${wsProto}//${window.location.host}/ws/live/${sessionSlug}?speed=${speed}&start=${startAt}`
      const ws = new WebSocket(url)
      wsRef.current = ws
      setStatus('connecting')

      ws.onopen = () => {
        if (!isCurrent) { ws.close(); return }
        setStatus('connected')
        retryDelay.current = 1000
      }

      ws.onmessage = (ev) => {
        if (!isCurrent) return
        try {
          const msg = JSON.parse(ev.data) as LiveSnapshot
          if (msg.badge != null) setBadge(msg.badge)
          onSnapshot(msg)
        } catch { /* ignore parse errors */ }
      }

      ws.onclose = () => {
        if (!isCurrent || !mountedRef.current) return
        wsRef.current = null
        setStatus('reconnecting')
        const delay = retryDelay.current
        retryDelay.current = Math.min(delay * 2, 30000)
        retryRef.current = setTimeout(connect, delay)
      }

      ws.onerror = () => {
        if (!isCurrent) return
        setStatus('error')
        ws.close()
      }
    }

    connect()
    return () => {
      isCurrent = false
      disconnect()
    }
  }, [sessionSlug, speed, startAt, enabled])

  // Periodically fetch subscriber count
  useEffect(() => {
    if (!enabled) return
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`/api/v1/live/${sessionSlug}/status`)
        if (r.ok) {
          const d = await r.json()
          setSubscriberCount(d.subscriber_count)
        }
      } catch { /* ignore */ }
    }, 5000)
    return () => clearInterval(interval)
  }, [sessionSlug, enabled])

  return { status, badge, subscriberCount }
}
