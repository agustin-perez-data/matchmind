import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from './api'
import type { CoachMsg, InsightMsg, MatchEvent, Meta, RiskMsg, RiskWindow, Snapshot, StreamStatus, ViewerProfile } from './types'

export type StreamOptions = {
  matchId: string
  speed: number
  profile: ViewerProfile
  agents: boolean
  coach: boolean
}

export type FeedItem = { id: string; at: number; msg: InsightMsg | CoachMsg }

export type StreamState = {
  status: StreamStatus
  meta: Meta | null
  snapshot: Snapshot | null
  lastEvent: MatchEvent | null
  trail: MatchEvent[] // recent events with coordinates, oldest first
  keyEvents: MatchEvent[] // newest first
  feed: FeedItem[] // newest first
  risk: RiskMsg | null
  alerts: RiskWindow[] // newest first
  agentsOn: boolean
  coachOn: boolean
  goalFlash: number
}

const EMPTY: StreamState = {
  status: 'idle', meta: null, snapshot: null, lastEvent: null, trail: [], keyEvents: [], feed: [],
  risk: null, alerts: [], agentsOn: false, coachOn: false, goalFlash: 0,
}

const KEY_TYPES = new Set(['goal', 'shot', 'card', 'injury_concern', 'substitution', 'tactical_change', 'half_time', 'full_time', 'kickoff', 'second_half_kickoff'])
const TRAIL = 28

export function useMatchStream() {
  const [state, setState] = useState<StreamState>(EMPTY)
  const ws = useRef<WebSocket | null>(null)

  const stop = useCallback(() => {
    ws.current?.close()
    ws.current = null
  }, [])

  const start = useCallback((opts: StreamOptions) => {
    stop()
    setState({ ...EMPTY, status: 'connecting' })
    const q = new URLSearchParams({
      speed: String(opts.speed), mode: opts.profile.mode, lang: opts.profile.language,
      agents: opts.agents ? '1' : '0', coach: opts.coach ? '1' : '0',
    })
    if (opts.profile.favorite_player_id) q.set('player', opts.profile.favorite_player_id)
    const socket = new WebSocket(wsUrl(`/ws/matches/${opts.matchId}?${q}`))
    ws.current = socket

    socket.onmessage = (m) => {
      const x = JSON.parse(m.data as string)
      setState((s) => {
        switch (x.kind) {
          case 'meta':
            return { ...s, status: 'live', meta: x.meta, agentsOn: x.agents, coachOn: x.coach }
          case 'event': {
            const e = x.event as MatchEvent
            const next: StreamState = { ...s, lastEvent: e }
            if (x.state) next.snapshot = x.state
            if (typeof e.x === 'number') next.trail = [...s.trail.slice(-(TRAIL - 1)), e]
            if (KEY_TYPES.has(e.type)) next.keyEvents = [e, ...s.keyEvents].slice(0, 80)
            if (e.type === 'goal') next.goalFlash = s.goalFlash + 1
            return next
          }
          case 'insight':
          case 'coach':
            return { ...s, feed: [{ id: `${x.kind}-${s.feed.length}-${x.clock}`, at: Date.now(), msg: x }, ...s.feed].slice(0, 60) }
          case 'risk':
            return { ...s, risk: x }
          case 'risk_alert':
            return { ...s, alerts: [x, ...s.alerts].slice(0, 40) }
          case 'end':
            return { ...s, status: 'ended', snapshot: x.state }
          default:
            return s
        }
      })
    }
    socket.onerror = () => setState((s) => ({ ...s, status: 'error' }))
    socket.onclose = () => setState((s) => (s.status === 'ended' ? s : { ...s, status: s.status === 'connecting' ? 'error' : s.status }))
  }, [stop])

  const send = useCallback((payload: Record<string, unknown>) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(payload))
  }, [])

  useEffect(() => () => stop(), [stop])

  return { state, start, stop, send }
}
