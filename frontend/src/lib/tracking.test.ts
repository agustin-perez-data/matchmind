import { describe, expect, it } from 'vitest'
import { HEAT_COLS, HEAT_ROWS, attacksRight, blockDiffSeries, blockLeader, convexHull, glideMs, heatCellRect, heatCells, heatCentroid, heatReading, lerpFrame, rosterKey, toAbsoluteX } from './tracking'
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

describe('convexHull', () => {
  it('returns the corners of a square in order and drops interior and collinear points', () => {
    const hull = convexHull([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5], [5, 0], [2, 8]])
    expect(hull).toEqual([[0, 0], [10, 0], [10, 10], [0, 10]])
  })
  it('passes through fewer than three points', () => {
    expect(convexHull([[3, 4], [1, 2]])).toEqual([[1, 2], [3, 4]])
    expect(convexHull([])).toEqual([])
  })
})

describe('lerpFrame', () => {
  const a: Frame = { kind: 'frame', period: 1, minute: 0, second: 0, ball: [0, 0], carrier: null, players: { A: [0, 0], B: [10, 10] } }
  const b: Frame = { kind: 'frame', period: 1, minute: 0, second: 1, ball: [0, 0], carrier: null, players: { A: [10, 20], C: [50, 50] } }
  it('interpolates and places newcomers where the second frame puts them', () => {
    expect(lerpFrame(a, b, 0.5)).toEqual({ A: [5, 10], C: [50, 50] })
    expect(lerpFrame(null, b, 0.2)).toEqual(b.players)
    expect(lerpFrame(a, b, 2).A).toEqual([10, 20])
  })
})

describe('block difference', () => {
  const meta = { home_id: 'THU', away_id: 'NBF' }
  const pt = (minute: number, h: number, a: number) => ({ period: 1, minute, THU: h, NBF: a })
  it('smooths home minus away with a trailing window and skips minutes missing a side', () => {
    const d = blockDiffSeries([pt(1, 40, 30), pt(2, 46, 30), { period: 1, minute: 3, THU: 50 }, pt(4, 52, 30)], meta)
    expect(d.map((p) => p.minute)).toEqual([1, 2, 4])
    expect(d.map((p) => Math.round(p.diff * 100) / 100)).toEqual([10, 13, 16]) // 10; (10+16)/2; (10+16+22)/3
  })
  it('is settling before five minutes, then names the side pinned back by 8 m or more', () => {
    const away = [1, 2, 3, 4, 5].map((m) => pt(m, 50, 32)) // home 18 m higher: away pinned back
    expect(blockLeader(blockDiffSeries(away.slice(0, 4), meta))).toEqual({ text: 'settling', side: null })
    expect(blockLeader(blockDiffSeries(away, meta))).toEqual({ text: 'pinned back', side: 'away' })
    expect(blockLeader(blockDiffSeries([1, 2, 3, 4, 5].map((m) => pt(m, 30, 45)), meta))).toEqual({ text: 'pinned back', side: 'home' })
    expect(blockLeader(blockDiffSeries([1, 2, 3, 4, 5].map((m) => pt(m, 40, 44)), meta))).toEqual({ text: 'even', side: null })
    expect(blockLeader([])).toEqual({ text: 'settling', side: null })
  })
  it('reads the smoothed last value, so one outlier minute does not flip it', () => {
    const steady = [1, 2, 3, 4, 5, 6].map((m) => pt(m, 40, 41))
    const spike = [...steady, pt(7, 70, 30)] // raw +40, smoothed (−1 −1 +40)/3 ≈ 12.7 → still pinned back; two steady minutes later it is even again
    expect(blockLeader(blockDiffSeries(spike, meta)).side).toBe('away')
    expect(blockLeader(blockDiffSeries([...spike, pt(8, 40, 41), pt(9, 40, 41)], meta)).side).toBe('away')
    expect(blockLeader(blockDiffSeries([...spike, pt(8, 40, 41), pt(9, 40, 41), pt(10, 40, 41)], meta)).side).toBeNull()
  })
})

describe('heatCentroid', () => {
  it('weights cell centres by occupancy', () => {
    const grid = new Array(HEAT_COLS * HEAT_ROWS).fill(0)
    grid[0] = 1 // column 0 row 0: centre (4.17, 6.25)
    grid[HEAT_COLS * HEAT_ROWS - 1] = 3 // column 11 row 7: centre (95.83, 93.75)
    const c = heatCentroid(grid)!
    expect(c[0]).toBeCloseTo((4.1667 + 3 * 95.8333) / 4, 2)
    expect(c[1]).toBeCloseTo((6.25 + 3 * 93.75) / 4, 2)
    expect(heatCentroid(new Array(96).fill(0))).toBeNull()
    expect(heatCentroid(undefined)).toBeNull()
  })
})
