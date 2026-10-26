import type { ViewerProfile } from './types'

/** Where you sit decides what the broadcast shows you and how the agents talk to you. */
export type Seat = 'fan' | 'analyst' | 'bench' | 'control'

export const SEATS: Record<Seat, { label: string; promise: string; firstThirtySeconds: string; start?: boolean; mode: ViewerProfile['mode']; rule: string }> = {
  control: {
    label: 'Control room',
    promise: 'Watch the agents work, moment by moment.',
    firstThirtySeconds: 'The pipeline map lights up on the first key moment; its swimlane shows the Analyst and Narrator running in parallel, tool calls and the guardrail verdict.',
    mode: 'commentator',
    rule: '#c084fc',
  },
  fan: {
    label: 'Fan',
    promise: 'Live commentary, the ball, the goals, in your language.',
    firstThirtySeconds: 'The pitch comes alive with 22 players, the commentator calls the first chance, and you can pick a player to follow.',
    start: true,
    mode: 'commentator',
    rule: '#ffffff',
  },
  analyst: {
    label: 'Analyst',
    promise: 'Why the match is going the way it goes, with the numbers.',
    firstThirtySeconds: 'Momentum and block height start moving; the Analyst explains the first key moment and makes a forecast the Judge will grade ten minutes later.',
    mode: 'analyst',
    rule: '#ffd166',
  },
  bench: {
    label: 'Bench',
    promise: 'Who is at risk, what to do, and what would have happened.',
    firstThirtySeconds: 'The readiness board ranks the eleven by hazard; the first risk window opens, the Coach proposes a change and the engine re-simulates the match.',
    mode: 'analyst',
    rule: '#2dd4bf',
  },
}

export const SEAT_ORDER: Seat[] = ['fan', 'analyst', 'bench', 'control']

export function parseSeat(value: string | null): Seat | null {
  return value === 'fan' || value === 'analyst' || value === 'bench' || value === 'control' ? value : null
}

export function profileForSeat(seat: Seat, language: ViewerProfile['language'], favoritePlayerId: string | null, teamId: string | null = null): ViewerProfile {
  const team = seat === 'fan' ? teamId : null
  if (seat === 'fan' && favoritePlayerId) return { mode: 'player_focus', language, favorite_player_id: favoritePlayerId, team_id: team }
  return { mode: SEATS[seat].mode, language, favorite_player_id: seat === 'fan' ? favoritePlayerId : null, team_id: team }
}

/** Profile spec for the socket: mode:lang:player:team */
export const profileSpec = (p: ViewerProfile) => `${p.mode}:${p.language}:${p.favorite_player_id ?? ''}:${p.team_id ?? ''}`

/** The Control room watches several viewers at once: the home fan (its own line), the away fan and an analyst. */
export function compareForSeat(seat: Seat, language: ViewerProfile['language'], awayId: string | null): ViewerProfile[] {
  if (seat !== 'control') return []
  const awayFan: ViewerProfile[] = awayId ? [{ mode: 'commentator', language, favorite_player_id: null, team_id: awayId }] : []
  return [...awayFan, { mode: 'analyst', language, favorite_player_id: null, team_id: null }]
}

/** The control seat's own viewer is the home fan when the fixture is known, a neutral commentator otherwise. */
export function controlProfile(language: ViewerProfile['language'], homeId: string | null): ViewerProfile {
  return { mode: 'commentator', language, favorite_player_id: null, team_id: homeId }
}
