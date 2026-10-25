import { describe, expect, it } from 'vitest'
import { availableSubs, currentHazard, decisionLog, describeBranch, effortDelta, nameOf, orderKey, readiness, subBudget, subbedOff, topHazards } from './bench'
import type { FeedItem } from './useMatchStream'
import type { BranchSummary, CoachMsg, MatchEvent, Meta, PlayerView, RiskWindow } from './types'

const sub = (n: number, team: string, period: number, minute: number, second = 10): MatchEvent =>
  ({ event_id: n, period, minute, second, clock: `${minute}:${second}`, type: 'substitution', team_id: team })

describe('subBudget', () => {
  it('counts changes and groups those made in the same stoppage into one window', () => {
    const b = subBudget([sub(1, 'THU', 2, 60), sub(2, 'THU', 2, 60), sub(3, 'THU', 2, 75), sub(4, 'NBF', 2, 70)], 'THU')
    expect(b).toEqual({ used: 3, left: 2, windows: 2, windowsLeft: 1, exhausted: false })
  })
  it('does not charge a window for the half-time break but still counts the change', () => {
    const b = subBudget([sub(1, 'THU', 2, 45, 0)], 'THU')
    expect(b).toEqual({ used: 1, left: 4, windows: 0, windowsLeft: 3, exhausted: false })
  })
  it('is exhausted when either the changes or the windows run out', () => {
    expect(subBudget([60, 70, 80].map((m, i) => sub(i, 'THU', 2, m)), 'THU').exhausted).toBe(true)
    expect(subBudget([1, 2, 3, 4, 5].map((i) => sub(i, 'THU', 2, 60)), 'THU')).toMatchObject({ used: 5, left: 0, windows: 1, exhausted: true })
    expect(subBudget([], 'THU')).toEqual({ used: 0, left: 5, windows: 0, windowsLeft: 3, exhausted: false })
  })
})

const player = (over: Partial<PlayerView>): PlayerView => ({
  player_id: 'THU-09', name: 'A', team_id: 'THU', position: 'MF', shirt_number: 9, on_pitch: true, minutes_played: 60, distance_m: 7000, sprints: 10, top_speed_kmh: 30,
  acwr_pre_match: 1, acwr_live: 1.1, risk_band: 'optimal', sprints_per_min: 0.2, effort_ratio: 1.0, effort_ratio_recent: 1.0, injury_concerns: 0, ...over,
})
const window: RiskWindow = { player_id: 'THU-09', name: 'A', team_id: 'THU', position: 'MF', open_minute: 39, expires_minute: 54, hazard: 0.6, level: 'elevated', clock: '39:00', minutes_played: 39, acwr_live: 1.2 }

describe('readiness', () => {
  it('ranks an open window above everything, then the high band, then a pace drop, then freshness', () => {
    expect(readiness(player({}), window)).toEqual({ state: 'at risk', reason: "elevated risk window since 39'" })
    expect(readiness(player({ risk_band: 'high', effort_ratio_recent: 0.5 })).state).toBe('at risk')
    expect(readiness(player({ effort_ratio_recent: 0.85 }))).toEqual({ state: 'fading', reason: 'recent pace 15% under own pace' })
    expect(readiness(player({ effort_ratio_recent: 0.85, minutes_played: 12 })).state).toBe('fresh') // too early to call a drop
    expect(readiness(player({ minutes_played: 8 }))).toEqual({ state: 'fresh', reason: "8' played" })
    expect(readiness(player({})).state).toBe('steady')
  })
})

describe('bench lists', () => {
  const players = {
    'THU-01': player({ player_id: 'THU-01', position: 'GK', on_pitch: true }),
    'THU-02': player({ player_id: 'THU-02', shirt_number: 2, position: 'GK', on_pitch: false, minutes_played: 0 }),
    'THU-15': player({ player_id: 'THU-15', shirt_number: 15, position: 'FW', on_pitch: false, minutes_played: 0 }),
    'THU-07': player({ player_id: 'THU-07', shirt_number: 7, position: 'DF', on_pitch: false, minutes_played: 0 }),
    'THU-09': player({ player_id: 'THU-09', position: 'MF', on_pitch: false, minutes_played: 58 }),
    'NBF-15': player({ player_id: 'NBF-15', team_id: 'NBF', position: 'FW', on_pitch: false, minutes_played: 0 }),
  }
  it('lists available substitutes by position then shirt, and the players taken off', () => {
    expect(availableSubs(players, 'THU').map((p) => p.player_id)).toEqual(['THU-02', 'THU-07', 'THU-15'])
    expect(subbedOff(players, 'THU').map((p) => p.player_id)).toEqual(['THU-09'])
  })
})

describe('hazard series', () => {
  const series = { 'THU-09': [[4, 0.2], [9, 0.55]] as [number, number][], 'THU-15': [[4, 0.7]] as [number, number][] }
  it('reads the last value and ranks players', () => {
    expect(currentHazard(series, 'THU-09')).toBe(0.55)
    expect(currentHazard(series, 'THU-99')).toBeNull()
    expect(topHazards(series, ['THU-09', 'THU-15', 'THU-99'], 5)).toEqual([{ pid: 'THU-15', hazard: 0.7 }, { pid: 'THU-09', hazard: 0.55 }])
  })
  it('reports the effort change against own pace only once there is enough play', () => {
    expect(effortDelta(player({ effort_ratio_recent: 0.88 }))).toBe(-12)
    expect(effortDelta(player({ minutes_played: 5 }))).toBeNull()
  })
  it('keys the board order on the sequence of ids only', () => {
    expect(orderKey(['a', 'b'])).toBe('a,b')
    expect(orderKey(['b', 'a'])).not.toBe(orderKey(['a', 'b']))
  })
})

// ---------------------------------------------------------------- decision log

const meta = {
  match_id: 'M', home_id: 'THU', away_id: 'NBF', score: {}, n_events: 0, seed: 1,
  teams: {
    THU: { team_id: 'THU', name: 'Thames United', short_name: 'Thames', primary_color: '#d0021b', style: 'possession', players: [
      { player_id: 'THU-15', name: 'Declan Silveira', position: 'FW', shirt_number: 15, starter: true },
      { player_id: 'THU-18', name: 'Idris Ojo', position: 'FW', shirt_number: 18, starter: false },
    ] },
    NBF: { team_id: 'NBF', name: 'Northbridge FC', short_name: 'Northbridge', primary_color: '#1e3a8a', style: 'direct', players: [] },
  },
} as unknown as Meta

const side = { score: { THU: 1, NBF: 1 }, xg: { THU: 1, NBF: 1 }, shots: {}, injury_concerns: {}, injury_concerns_total: 3, goals: [] }
const branch = (id: string, minute: number, off = 'THU-15'): BranchSummary => ({
  branch_id: id, match_id: 'M', status: 'applied', intervention: { minute, type: 'substitution', team_id: 'THU', player_off_id: off, reason: 'coach' },
  divergence_minute: minute, actual: side, branch: side, diff: { goals_home: 0, goals_away: 0, xg_home: 0, xg_away: 0, injury_concerns: -1 }, branch_event_count: 100,
} as unknown as BranchSummary)
const coachMsg = (clock: string, minute: number, action: 'substitution' | 'hold', b: BranchSummary | null): CoachMsg => ({
  kind: 'coach', trigger: 'risk_alert', clock, minute, score: {}, player: { player_id: 'THU-15', name: 'Declan Silveira' },
  proposal: action === 'hold' ? { action: 'hold', minute, rationale: '' } : { action: 'substitution', minute, player_off_id: 'THU-15', player_on_id: 'THU-18', rationale: '' },
  branch: b, errors: [], latency_ms: 0,
} as unknown as CoachMsg)
const item = (id: string, msg: CoachMsg): FeedItem => ({ id, at: 0, msg })

describe('decisionLog', () => {
  it('merges Coach proposals and bench branches in match order, newest-first feed in', () => {
    const feed = [item('c2', coachMsg('74:57', 74, 'hold', null)), item('c1', coachMsg('57:34', 57, 'substitution', branch('b1', 58)))]
    const log = decisionLog(feed, [branch('u1', 50), branch('b1', 58)], meta)
    expect(log.map((e) => `${e.minute}:${e.source}`)).toEqual(['50:bench', '57:coach', '74:coach'])
    expect(log[1]).toMatchObject({ trigger: 'risk window', player: 'Declan Silveira', decision: "Declan Silveira off at 57', Idris Ojo on" })
    expect(log[2]).toMatchObject({ decision: 'hold', branch: null })
    expect(log[0].decision).toBe("What if Declan Silveira comes off at 50'")
  })
  it('describes branches and falls back to the id for unknown players', () => {
    expect(describeBranch(meta, { ...branch('x', 70), intervention: { minute: 70, type: 'tactic', team_id: 'NBF', reason: 'coach' } } as unknown as BranchSummary)).toBe("What if Northbridge changes tactics at 70'")
    expect(nameOf(meta, 'THU-99')).toBe('THU-99')
    expect(nameOf(meta, null)).toBe('?')
  })
})
