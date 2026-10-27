import { describe, expect, it } from 'vitest'
import type { MatchRow } from './api'
import { headlineFixture, isDaily, menuFixtures, quickStartPlan } from './fixtures'

const row = (id: string) => ({ match_id: id, home_id: id.slice(0, 3), away_id: id.slice(4, 7) }) as MatchRow

describe('menu fixtures', () => {
  it('derby first, then the matchday, then only the newest daily match', () => {
    const rows = [row('CRC-ALV-47'), row('ALV-CRC-20261026'), row('THU-NBF-40'), row('IRA-MRV-21'), row('KPF-THU-20261027'), row('TGW-KPF-46')]
    const menu = menuFixtures(rows)
    expect(menu.map((f) => f.row.match_id)).toEqual(['THU-NBF-40', 'CRC-ALV-47', 'IRA-MRV-21', 'TGW-KPF-46', 'KPF-THU-20261027'])
    expect(menu.map((f) => f.daily)).toEqual([false, false, false, false, true])
  })

  it('a catalogue without a derby still has a headline', () => {
    expect(headlineFixture([row('CRC-ALV-47'), row('IRA-MRV-21')])?.match_id).toBe('CRC-ALV-47')
    expect(headlineFixture([])).toBeNull()
    expect(menuFixtures([])).toEqual([])
  })

  it('recognises the nightly job ids by their date suffix', () => {
    expect(isDaily('ALV-CRC-20261026')).toBe(true)
    expect(isDaily('THU-NBF-40')).toBe(false)
  })
})

describe('the primary action', () => {
  it('opens the derby in the fan seat, neutral, even when another fixture is selected', () => {
    const plan = quickStartPlan([row('CRC-ALV-47'), row('THU-NBF-40')], 'CRC-ALV-47', 'es', 60, true, true)
    expect(plan?.matchId).toBe('THU-NBF-40')
    expect(plan?.url).toMatchObject({ seat: 'fan', match: 'THU-NBF-40', lang: 'es', speed: '60', team: 'neutral', agents: null, coach: null })
  })

  it('falls back to the first listed fixture, then to the selection, and keeps agent flags', () => {
    expect(quickStartPlan([row('CRC-ALV-47')], null, 'en', 60, false, true)?.url).toMatchObject({ match: 'CRC-ALV-47', agents: '0', coach: null })
    expect(quickStartPlan([], 'IRA-MRV-21', 'en', 60, true, true)?.matchId).toBe('IRA-MRV-21')
    expect(quickStartPlan([], null, 'en', 60, true, true)).toBeNull()
  })
})
