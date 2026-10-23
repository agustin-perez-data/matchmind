/** What a fan wants to know about the player they follow, derived from the raw event stream. */

import type { MatchEvent, Meta } from './types'

/** Event types that count as the player touching the ball or doing something a fan notices. */
export const TOUCH_TYPES = new Set(['pass', 'shot', 'goal', 'tackle', 'interception'])
export const KEEP_TYPES = new Set([...TOUCH_TYPES, 'injury_concern', 'substitution', 'card'])

/** The slice of an event worth keeping for the whole match (the stream has ~2,000 of them). */
export type Touch = Pick<MatchEvent, 'event_id' | 'clock' | 'minute' | 'period' | 'type' | 'team_id' | 'player_id' | 'player_name' | 'x' | 'y' | 'end_x' | 'end_y' | 'outcome' | 'xg' | 'detail' | 'card'> & {
  receiver_id?: string
  assist_player_id?: string
  player_off_id?: string
  player_on_id?: string
}

export function keep(e: MatchEvent & Partial<Touch>): Touch | null {
  if (!KEEP_TYPES.has(e.type)) return null
  return {
    event_id: e.event_id, clock: e.clock, minute: e.minute, period: e.period, type: e.type, team_id: e.team_id,
    player_id: e.player_id, player_name: e.player_name, x: e.x, y: e.y, end_x: e.end_x, end_y: e.end_y,
    outcome: e.outcome, xg: e.xg, detail: e.detail, card: e.card,
    receiver_id: e.receiver_id, assist_player_id: e.assist_player_id, player_off_id: e.player_off_id, player_on_id: e.player_on_id,
  }
}

/** Everything the player was part of: their own actions, assists, and being subbed off/on. */
export function playerEvents(events: Touch[], id: string): Touch[] {
  return events.filter((e) => e.player_id === id || e.assist_player_id === id || e.player_off_id === id || e.player_on_id === id)
}

export type FanStats = {
  touches: number
  passes: number
  passesCompleted: number
  shots: number
  onTarget: number
  goals: number
  assists: number
  xg: number
  keyPasses: number
  tackles: number
  interceptions: number
}

/** Numbers a fan cares about. A key pass is a completed pass whose receiver shot within the next three events.
 *  The stream emits a shot with outcome "goal" AND a goal event for the same strike: goals and assists are
 *  counted from the goal events only, the shot counts as a shot. */
export function fanStats(events: Touch[], id: string): FanStats {
  const s: FanStats = { touches: 0, passes: 0, passesCompleted: 0, shots: 0, onTarget: 0, goals: 0, assists: 0, xg: 0, keyPasses: 0, tackles: 0, interceptions: 0 }
  events.forEach((e, i) => {
    if (e.type === 'goal' && e.assist_player_id === id) s.assists++
    if (e.player_id !== id) return
    if (TOUCH_TYPES.has(e.type)) s.touches++
    switch (e.type) {
      case 'pass':
        s.passes++
        if (e.outcome === 'complete' || e.outcome === 'completed') {
          s.passesCompleted++
          const next = events.slice(i + 1, i + 4)
          if (e.receiver_id && next.some((n) => (n.type === 'shot' || n.type === 'goal') && n.player_id === e.receiver_id)) s.keyPasses++
        }
        break
      case 'shot':
        s.shots++
        s.xg += e.xg ?? 0
        if (e.outcome === 'goal' || e.outcome === 'saved') s.onTarget++
        break
      case 'goal':
        s.goals++
        break
      case 'tackle': s.tackles++; break
      case 'interception': s.interceptions++; break
    }
  })
  s.xg = Math.round(s.xg * 100) / 100
  return s
}

export type TickerLine = { event_id: number; clock: string; text: string; big: boolean }

const last = (name?: string) => (name ?? '').split(' ').slice(-1)[0]

/** The player's match as a fan would tell it, newest first, quiet passes left out. */
export function ticker(events: Touch[], id: string, meta: Meta, limit = 8): TickerLine[] {
  const name = (pid?: string) => last(Object.values(meta.teams).flatMap((t) => t.players).find((p) => p.player_id === pid)?.name) || pid || '?'
  const out: TickerLine[] = []
  events.forEach((e, i) => {
    let text: string | null = null, big = false
    if (e.player_id === id) {
      switch (e.type) {
        case 'goal':
          // the shot line just before already says GOAL with its xG; only speak when there was no such shot
          if (!events.slice(Math.max(0, i - 3), i).some((p) => p.type === 'shot' && p.outcome === 'goal' && p.player_id === id)) { text = 'GOAL'; big = true }
          break
        case 'shot':
          text = e.outcome === 'goal' ? `GOAL, ${e.xg != null ? `xG ${e.xg.toFixed(2)}` : 'finished'}` : e.outcome === 'saved' ? `shot saved${e.xg != null ? `, xG ${e.xg.toFixed(2)}` : ''}` : e.outcome === 'blocked' ? 'shot blocked' : 'shot off target'
          big = e.outcome === 'goal'
          break
        case 'tackle': text = 'won a tackle'; break
        case 'interception': text = 'intercepted'; break
        case 'injury_concern': text = `a worry: ${e.detail ?? 'receiving treatment'}`; big = true; break
        case 'card': text = `${e.card ?? 'yellow'} card`; big = e.card === 'red'; break
        case 'pass': {
          const next = events.slice(i + 1, i + 4)
          const shot = e.receiver_id ? next.find((n) => (n.type === 'shot' || n.type === 'goal') && n.player_id === e.receiver_id) : undefined
          if (shot) text = `key pass to ${name(e.receiver_id)}${shot.outcome === 'goal' ? ', and it went in' : ''}`
          break
        }
      }
    } else if (e.type === 'goal' && e.assist_player_id === id) {
      text = `ASSIST for ${name(e.player_id)}`; big = true
    } else if (e.player_off_id === id) {
      text = `subbed off${e.player_on_id ? `, ${name(e.player_on_id)} on` : ''}`; big = true
    } else if (e.player_on_id === id) {
      text = `comes on${e.player_off_id ? ` for ${name(e.player_off_id)}` : ''}`; big = true
    }
    if (text) out.push({ event_id: e.event_id, clock: e.clock, text, big })
  })
  return out.reverse().slice(0, limit)
}

/** Touch map points: where the player acted on the ball (pitch coordinates, 0-100). */
export function touchPoints(events: Touch[], id: string): { x: number; y: number; type: string; event_id: number }[] {
  return events.filter((e) => e.player_id === id && TOUCH_TYPES.has(e.type) && typeof e.x === 'number' && typeof e.y === 'number')
    .map((e) => ({ x: e.x as number, y: e.y as number, type: e.type, event_id: e.event_id }))
}
