import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from './api'
import { keep, type Touch } from './follow'
import type { CoachMsg, Credibility, Frame, InsightMsg, MatchEvent, Meta, RiskMsg, RiskWindow, Snapshot, StreamStatus, VerdictMsg, ViewerProfile } from './types'

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
  touches: Touch[] // every on-ball action and knock/sub/card of the match, oldest first (for the followed player)
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
  status: 'idle', meta: null, snapshot: null, lastEvent: null, ball: [], shots: [], keyEvents: [], touches: [], feed: [],
  risk: null, alerts: [], verdicts: [], credibility: null, agentsOn: false, coachOn: false, goalFlash: 0,
}

const KEY_TYPES = new Set(['goal', 'shot', 'card', 'injury_concern', 'substitution', 'tactical_change', 'half_time', 'full_time', 'kickoff', 'second_half_kickoff'])
const BALL_TRAIL = 6
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 16000]

export function useMatchStream() {
  const [state, setState] = useState<StreamState>(EMPTY)
  const ws = useRef<WebSocket | null>(null)
  // positional frames: up to one per match second, read by the tracking layer on its own animation loop; never React state
  const frameRef = useRef<Frame | null>(null)

  const stop = useCallback(() => {
    manualClose.current = true
    running.current = null
    ws.current?.close()
    ws.current = null
    setState((s) => (s.status === 'idle' ? s : { ...s, status: 'idle' }))
  }, [])

  // resume bookkeeping: the last event id we saw, the options of the running stream, and whether the close was ours
  const lastEventId = useRef<number | null>(null)
  const running = useRef<StreamOptions | null>(null)
  const manualClose = useRef(false)
  const attempts = useRef(0)
  const everConnected = useRef(false)  // a first connection that never opens is an error, a lost one is a reconnect
  const ended = useRef(false)  // the server closes cleanly after `end`: that is not a loss

  const connect = useCallback((opts: StreamOptions, resumeFrom: number | null) => {
    let frames = 0
    const q = new URLSearchParams({
      speed: String(opts.speed), mode: opts.profile.mode, lang: opts.profile.language,
      agents: opts.agents ? '1' : '0', coach: opts.coach ? '1' : '0',
      min_importance: String(opts.minImportance ?? 3),
    })
    if (opts.profile.favorite_player_id) q.set('player', opts.profile.favorite_player_id)
    if (opts.profile.team_id) q.set('team', opts.profile.team_id)
    if (opts.compare && opts.compare.length) q.set('compare', opts.compare.map((c) => `${c.mode}:${c.language}:${c.favorite_player_id ?? ''}:${c.team_id ?? ''}`).join(','))
    if (resumeFrom != null) q.set('from', String(resumeFrom))
    const socket = new WebSocket(wsUrl(`/ws/matches/${opts.matchId}?${q}`))
    ws.current = socket

    socket.onmessage = (m) => {
      const x = JSON.parse(m.data as string)
      if (x.kind === 'frame') {
        x.at = performance.now()
        frameRef.current = x as Frame
        frames += 1
        if (import.meta.env.DEV) (window as unknown as { __frames?: number }).__frames = frames
        return
      }
      if (x.kind === 'event') lastEventId.current = (x.event as MatchEvent).event_id
      else if (x.kind === 'meta') { everConnected.current = true; attempts.current = 0 }
      else if (x.kind === 'end') ended.current = true
      setState((s) => {
        switch (x.kind) {
          case 'meta':
            return { ...s, status: 'live', meta: x.meta, agentsOn: x.agents, coachOn: x.coach }
          case 'resume':
            // the server rebuilt the state up to our last event on another replica: take its snapshot, keep our feed
            return { ...s, snapshot: x.state }
          case 'event': {
            const e = x.event as MatchEvent
            const next: StreamState = { ...s, lastEvent: e }
            if (x.state) next.snapshot = x.state
            if (typeof e.x === 'number') next.ball = [...s.ball.slice(-(BALL_TRAIL - 1)), { x: e.end_x ?? e.x, y: e.end_y ?? (e.y as number), team_id: e.team_id }]
            if (e.type === 'shot') next.shots = [...s.shots, e]
            const t = keep(e)
            if (t) next.touches = [...s.touches, t]
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
          case 'end': {
            // the last workload batch lands after full time and never gets its own risk message: merge the final summary here
            const risk = x.risk ? ({ ...(s.risk ?? { kind: 'risk', minute: x.state.minute, clock: x.state.clock, hazards_top: [], recent_alerts: [], concerns: [], note: '' }), ...x.risk, kind: 'risk', clock: x.state.clock, hazard_series: x.hazard_series ?? s.risk?.hazard_series } as RiskMsg) : s.risk
            return { ...s, status: 'ended', snapshot: x.state, credibility: x.credibility ?? s.credibility, risk }
          }
          default:
            return s
        }
      })
    }
    socket.onerror = () => { if (!everConnected.current) setState((s) => (s.status === 'connecting' ? { ...s, status: 'error' } : s)) }
    // side effects stay out of the state updaters (React may run an updater twice in development)
    socket.onclose = () => {
      if (ws.current !== socket) return  // superseded by a newer socket (start/stop): nothing to do
      if (manualClose.current || !running.current || ended.current) return
      if (!everConnected.current || attempts.current >= RECONNECT_DELAYS_MS.length) {
        setState((s) => (s.status === 'ended' || s.status === 'idle' ? s : { ...s, status: 'error' }))
        return
      }
      // the replica went away mid-replay (a deploy, a scale-in): come back where we were, with backoff
      const delay = RECONNECT_DELAYS_MS[attempts.current++]
      setState((s) => (s.status === 'live' || s.status === 'reconnecting' ? { ...s, status: 'reconnecting' } : s))
      setTimeout(() => {
        if (!manualClose.current && running.current && ws.current === socket && !ended.current) connect(running.current, lastEventId.current)
      }, delay)
    }
  }, [])

  const start = useCallback((opts: StreamOptions) => {
    manualClose.current = true
    ws.current?.close()
    manualClose.current = false
    setState({ ...EMPTY, status: 'connecting' })
    frameRef.current = null
    lastEventId.current = null
    attempts.current = 0
    everConnected.current = false
    ended.current = false
    running.current = opts
    connect(opts, null)
  }, [connect])

  const send = useCallback((payload: Record<string, unknown>) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(payload))
  }, [])

  useEffect(() => () => { ws.current?.close() }, [])

  return { state, start, stop, send, frameRef }
}
