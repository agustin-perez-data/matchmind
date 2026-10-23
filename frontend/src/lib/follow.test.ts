import { describe, expect, it } from 'vitest'
import { fanStats, keep, playerEvents, ticker, touchPoints, type Touch } from './follow'
import type { Meta } from './types'

const meta = {
  match_id: 'M', home_id: 'THU', away_id: 'NBF', score: {}, n_events: 0, seed: 1,
  teams: {
    THU: { team_id: 'THU', name: 'Thames United', short_name: 'Thames', primary_color: '#d0021b', style: 'possession', players: [
      { player_id: 'THU-15', name: 'Declan Silveira', position: 'FW', shirt_number: 15, starter: true },
      { player_id: 'THU-17', name: 'Kai Ferrant', position: 'FW', shirt_number: 17, starter: true },
      { player_id: 'THU-21', name: 'Felix Whitlow', position: 'MF', shirt_number: 21, starter: false },
    ] },
    NBF: { team_id: 'NBF', name: 'Northbridge FC', short_name: 'Northbridge', primary_color: '#1e3a8a', style: 'direct', players: [] },
  },
} as unknown as Meta

const ev = (n: number, type: string, extra: Partial<Touch> = {}): Touch => ({ event_id: n, clock: `${n}:00`, minute: n, period: 1, type, team_id: 'THU', player_id: 'THU-15', x: 50, y: 50, ...extra })

const events: Touch[] = [
  ev(1, 'pass', { outcome: 'complete', receiver_id: 'THU-17', x: 30, y: 40 }),
  ev(2, 'shot', { player_id: 'THU-17', outcome: 'saved', xg: 0.3 }),          // key pass for Silveira
  ev(3, 'pass', { outcome: 'incomplete', receiver_id: 'THU-17' }),
  ev(4, 'tackle', { x: 20, y: 60 }),
  ev(5, 'shot', { outcome: 'blocked', xg: 0.1, x: 80, y: 45 }),
  ev(6, 'shot', { outcome: 'goal', xg: 0.4, x: 88, y: 50, assist_player_id: 'THU-17' }),
  { ...ev(6, 'goal', { assist_player_id: 'THU-17' }), event_id: 61 },        // the stream repeats the strike as a goal event
  ev(7, 'shot', { player_id: 'THU-17', outcome: 'goal', xg: 0.2, assist_player_id: 'THU-15' }),
  { ...ev(7, 'goal', { player_id: 'THU-17', assist_player_id: 'THU-15' }), event_id: 71 },  // Silveira assists Ferrant
  ev(8, 'pass', { player_id: 'NBF-1', team_id: 'NBF', outcome: 'complete' }),
  ev(9, 'interception', { x: 40, y: 55 }),
  ev(10, 'substitution', { player_id: undefined, player_off_id: 'THU-15', player_on_id: 'THU-21' }),
]

describe('keep', () => {
  it('keeps only the event types a fan notices, trimmed to the fields used', () => {
    expect(keep({ event_id: 1, period: 1, minute: 1, second: 0, clock: '1:00', type: 'pressure' })).toBeNull()
    const k = keep({ event_id: 1, period: 1, minute: 1, second: 0, clock: '1:00', type: 'pass', player_id: 'A', receiver_id: 'B', x: 1, y: 2 } as never)
    expect(k).toMatchObject({ type: 'pass', player_id: 'A', receiver_id: 'B', x: 1, y: 2 })
    expect(k && 'second' in k).toBe(false)
  })
})

describe('playerEvents', () => {
  it('includes own actions, assists and substitutions', () => {
    const ids = playerEvents(events, 'THU-15').map((e) => e.event_id)
    expect(ids).toEqual([1, 3, 4, 5, 6, 61, 7, 71, 9, 10]) // 7: the shot Silveira assisted
    expect(playerEvents(events, 'THU-21').map((e) => e.event_id)).toEqual([10])
  })
})

describe('fanStats', () => {
  it('counts touches, shots, goals, assists, xG, key passes and defensive actions, without double counting a strike', () => {
    const s = fanStats(events, 'THU-15')
    expect(s).toEqual({ touches: 7, passes: 2, passesCompleted: 1, shots: 2, onTarget: 1, goals: 1, assists: 1, xg: 0.5, keyPasses: 1, tackles: 1, interceptions: 1 })
    expect(fanStats(events, 'THU-17')).toMatchObject({ goals: 1, assists: 1, shots: 2 })
  })
  it('is all zeros for someone who did nothing', () => {
    expect(fanStats(events, 'NBF-9').touches).toBe(0)
  })
})

describe('ticker', () => {
  it('tells the player match newest first, big moments flagged, quiet passes left out', () => {
    const lines = ticker(events, 'THU-15', meta)
    expect(lines.map((l) => l.text)).toEqual([
      'subbed off, Whitlow on', 'intercepted', 'ASSIST for Ferrant', 'GOAL, xG 0.40', 'shot blocked', 'won a tackle', 'key pass to Ferrant',
    ])
    expect(lines.filter((l) => l.big).map((l) => l.text)).toEqual(['subbed off, Whitlow on', 'ASSIST for Ferrant', 'GOAL, xG 0.40'])
    // a bare goal event with no shot before it still gets a line
    expect(ticker([{ ...ev(3, 'goal') }], 'THU-15', meta)[0].text).toBe('GOAL')
    expect(ticker(events, 'THU-15', meta, 2)).toHaveLength(2)
  })
  it('names the substitute coming on', () => {
    expect(ticker(events, 'THU-21', meta)[0].text).toBe('comes on for Silveira')
  })
})

describe('touchPoints', () => {
  it('returns pitch coordinates of the player on-ball actions only', () => {
    const pts = touchPoints(events, 'THU-15')
    expect(pts.map((p) => p.event_id)).toEqual([1, 3, 4, 5, 6, 61, 9])
    expect(pts[0]).toEqual({ x: 30, y: 40, type: 'pass', event_id: 1 })
  })
})
