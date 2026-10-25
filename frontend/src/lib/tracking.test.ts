import { describe, expect, it } from 'vitest'
import { HEAT_COLS, HEAT_ROWS, attacksRight, glideMs, heatCellRect, heatCells, heatReading, rosterKey, toAbsoluteX } from './tracking'
import type { Frame } from './types'

const frame = (players: string[]): Frame => ({ kind: 'frame', period: 1, minute: 0, second: 0, ball: [50, 50], carrier: null, players: Object.fromEntries(players.map((p) => [p, [50, 50] as [number, number]])) })

describe('rosterKey', () => {
  it('changes only when the set of players changes, not when they move', () => {
    const a = frame(['THU-01', 'NBF-01'])
    const moved: Frame = { ...a, players: { 'NBF-01': [10, 10], 'THU-01': [90, 90] } }
    expect(rosterKey(a)).toBe(rosterKey(moved))
    expect(rosterKey(frame(['THU-01', 'NBF-02']))).not.toBe(rosterKey(a))
    expect(rosterKey(null)).toBe('')
  })
})

describe('glideMs', () => {
  it('glides a near-second at x1, snaps at x60 and beyond, and never animates at max', () => {
    expect(glideMs(1)).toBe(900)
    expect(glideMs(15)).toBe(67)
    expect(glideMs(60)).toBe(17)
    expect(glideMs(300)).toBe(3)
    expect(glideMs(0)).toBe(0)
    expect(glideMs(Number.NaN)).toBe(0)
  })
})

describe('directions', () => {
  it('home attacks right in the first half and left in the second', () => {
    const meta = { home_id: 'THU' }
    expect(attacksRight(meta, 'THU', 1)).toBe(true)
    expect(attacksRight(meta, 'THU', 2)).toBe(false)
    expect(attacksRight(meta, 'NBF', 1)).toBe(false)
    expect(attacksRight(meta, 'NBF', 2)).toBe(true)
    expect(toAbsoluteX(80, true)).toBe(80)
    expect(toAbsoluteX(80, false)).toBe(20)
  })
})

describe('heat', () => {
  const grid = new Array(HEAT_COLS * HEAT_ROWS).fill(0)
  grid[2 * HEAT_COLS + 10] = 30 // row 2 (left channel), column 10 (final third)
  grid[2 * HEAT_COLS + 9] = 10

  it('places a team-frame cell on the pitch for either direction', () => {
    const r = heatCellRect(2 * HEAT_COLS + 10, true)
    expect(r.x).toBeCloseTo(1000 / 12)
    expect([r.y, r.w, r.h]).toEqual([25, 100 / 12, 12.5])
    expect(heatCellRect(2 * HEAT_COLS + 10, false).x).toBeCloseTo(100 - 1000 / 12 - 100 / 12)
  })

  it('normalises cells against the busiest one and skips empty cells', () => {
    const cells = heatCells(grid)
    expect(cells).toHaveLength(2)
    expect(cells.find((c) => c.index === 2 * HEAT_COLS + 10)).toEqual({ index: 34, share: 0.75, level: 1 })
    expect(cells.find((c) => c.index === 2 * HEAT_COLS + 9)?.level).toBeCloseTo(1 / 3)
    expect(heatCells(undefined)).toEqual([])
    expect(heatCells(new Array(96).fill(0))).toEqual([])
    expect(heatCells([1, 2, 3])).toEqual([])
  })

  it('reads the channel and the third in plain words', () => {
    expect(heatReading(grid)).toBe('most of the match in the left channel of the final third')
    expect(heatReading(new Array(96).fill(0))).toBeNull()
    expect(heatReading(null)).toBeNull()
  })
})
