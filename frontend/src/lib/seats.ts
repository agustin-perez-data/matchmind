import type { ViewerProfile } from './types'

/** Where you sit decides what the broadcast shows you and how the agents talk to you. */
export type Seat = 'fan' | 'analyst' | 'bench' | 'control'

export const SEATS: Record<Seat, { label: string; tagline: string; bullets: string[]; mode: ViewerProfile['mode']; rule: string }> = {
  control: {
    label: 'Control room',
    tagline: 'Watch the agents work.',
    bullets: ['Every key moment as a swimlane: Analyst and Narrator in parallel, Director after', 'Tool calls, latencies and the orchestration behind them', 'What the Director showed and hid, and why'],
    mode: 'commentator',
    rule: '#c084fc',
  },
  fan: {
    label: 'Fan',
    tagline: 'Live commentary, the ball, the goals.',
    bullets: ['A commentator in your language, rioplatense included', 'The pitch, the score and the momentum', 'Follow one player if you want'],
    mode: 'commentator',
    rule: '#ffffff',
  },
  analyst: {
    label: 'Analyst',
    tagline: 'Why the match is going the way it goes.',
    bullets: ['The Analyst agent explains every key moment', 'xG race, momentum and the stats that matter', 'A shot map sized by expected goals'],
    mode: 'analyst',
    rule: '#ffd166',
  },
  bench: {
    label: 'Bench',
    tagline: 'Who is at risk, what to do, what would have happened.',
    bullets: ['The Risk Monitor, graded live against real knocks', 'Coach proposals on every high-risk window', 'What-if branches you can simulate yourself'],
    mode: 'analyst',
    rule: '#2dd4bf',
  },
}

export const SEAT_ORDER: Seat[] = ['fan', 'analyst', 'bench', 'control']

export function parseSeat(value: string | null): Seat | null {
  return value === 'fan' || value === 'analyst' || value === 'bench' || value === 'control' ? value : null
}

export function profileForSeat(seat: Seat, language: ViewerProfile['language'], favoritePlayerId: string | null): ViewerProfile {
  if (seat === 'fan' && favoritePlayerId) return { mode: 'player_focus', language, favorite_player_id: favoritePlayerId }
  return { mode: SEATS[seat].mode, language, favorite_player_id: seat === 'fan' ? favoritePlayerId : null }
}

/** The Control room watches two viewers at once: its own commentator line and an analyst, same language. */
export function compareForSeat(seat: Seat, language: ViewerProfile['language']): ViewerProfile | null {
  return seat === 'control' ? { mode: 'analyst', language, favorite_player_id: null } : null
}
