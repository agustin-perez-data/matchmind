import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from './api'
import type { CoachMsg, Credibility, InsightMsg, MatchEvent, Meta, RiskMsg, RiskWindow, Snapshot, StreamStatus, VerdictMsg, ViewerProfile } from './types'

export type StreamOptions = {
  matchId: string
  speed: number
  profile: ViewerProfile
  agents: boolean
  coach: boolean
  minImportance?: number
  compare?: ViewerProfile[] // extra viewers explained side by side (Control room)
}

export type FeedItem = { id: string; at: number; msg: InsightMsg | CoachMsg }
export type VerdictItem = { id: string; at: number; msg: VerdictMsg }
export type BallPoint = { x: number; y: number; team_id?: string }

export type StreamState = {
  status: StreamStatus
  meta: Meta | null
  snapshot: Snapshot | null
  lastEvent: MatchEvent | null
  ball: BallPoint[] // recent ball positions, oldest first
  shots: MatchEvent[] // every shot so far, oldest first
  keyEvents: MatchEvent[] // newest first
  feed: FeedItem[] // newest first
  risk: RiskMsg | null
  alerts: RiskWindow[] // newest first
  verdicts: VerdictItem[] // the Judge's graded forecasts, newest first
  credibility: Credibility | null
  agentsOn: boolean
  coachOn: boolean
  goalFlash: number
}

const EMPTY: StreamState = {
  status: 'idle', meta: null, snapshot: null, lastEvent: null, ball: [], shots: [], keyEvents: [], feed: [],
  risk: null, alerts: [], verdicts: [], credibility: null, agentsOn: false, coachOn: false, goalFlash: 0,
}

const KEY_TYPES = new Set(['goal', 'shot', 'card', 'injury_concern', 'substitution', 'tactical_change', 'half_time', 'full_time', 'kickoff', 'second_half_kickoff'])
const BALL_TRAIL = 6

export function useMatchStream() {
  const [state, setState] = useState<StreamState>(EMPTY)
  const ws = useRef<WebSocket | null>(null)

  const stop = useCallback(() => {
    ws.current?.close()
    ws.current = null
    setState((s) => (s.status === 'idle' ? s : { ...s, status: 'idle' }))
  }, [])

  const start = useCallback((opts: StreamOptions) => {
    ws.current?.close()
    setState({ ...EMPTY, status: 'connecting' })
    const q = new URLSearchParams({
      speed: String(opts.speed), mode: opts.profile.mode, lang: opts.profile.language,
      agents: opts.agents ? '1' : '0', coach: opts.coach ? '1' : '0',
      min_importance: String(opts.minImportance ?? 3),
    })
    if (opts.profile.favorite_player_id) q.set('player', opts.profile.favorite_player_id)
    if (opts.profile.team_id) q.set('team', opts.profile.team_id)
    if (opts.compare && opts.compare.length) q.set('compare', opts.compare.map((c) => `${c.mode}:${c.language}:${c.favorite_player_id ?? ''}:${c.team_id ?? ''}`).join(','))
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
            if (typeof e.x === 'number') next.ball = [...s.ball.slice(-(BALL_TRAIL - 1)), { x: e.end_x ?? e.x, y: e.end_y ?? (e.y as number), team_id: e.team_id }]
            if (e.type === 'shot') next.shots = [...s.shots, e]
            if (KEY_TYPES.has(e.type)) next.keyEvents = [e, ...s.keyEvents].slice(0, 120)
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
          case 'verdict':
            return { ...s, verdicts: [{ id: `verdict-${x.event_id}`, at: Date.now(), msg: x }, ...s.verdicts].slice(0, 40), credibility: x.credibility ?? s.credibility }
          case 'end':
            return { ...s, status: 'ended', snapshot: x.state, credibility: x.credibility ?? s.credibility }
          default:
            return s
        }
      })
    }
    socket.onerror = () => setState((s) => ({ ...s, status: 'error' }))
    socket.onclose = () => setState((s) => (s.status === 'connecting' ? { ...s, status: 'error' } : s))
  }, [])

  const send = useCallback((payload: Record<string, unknown>) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(payload))
  }, [])

  useEffect(() => () => { ws.current?.close() }, [])

  return { state, start, stop, send }
}
