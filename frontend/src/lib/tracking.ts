/** Positional frames on the client: pure helpers for the tracking layer, the heat map and the player card.
 *
 * Positions come from a positional model built on the event stream (backend/matchmind/sim/tracking.py),
 * not from a tracking feed. Frames never enter React state: the layer reads them from a ref on every
 * animation frame; only these helpers are unit-tested.
 */

import type { Frame, Meta } from './types'

export const HEAT_COLS = 12
export const HEAT_ROWS = 8
/** A frame older than this (wall clock) means frames stopped: speed above the stride ceiling, or none requested. */
export const STALE_MS = 2500

/** Changes only when the set of players on the pitch changes (substitutions): the layer re-renders its dots then. */
export function rosterKey(frame: Frame | null): string {
  return frame ? Object.keys(frame.players).sort().join(',') : ''
}

/** How long a dot glides between frames: a near-second at x1, a snap at x60 and beyond, nothing at max. */
export function glideMs(speed: number): number {
  if (!Number.isFinite(speed) || speed <= 0) return 0
  return Math.round(Math.min(900, 1000 / speed))
}

/** Whether a team attacks left to right in a period: the home side attacks right in the first half. */
export function attacksRight(meta: Pick<Meta, 'home_id'>, teamId: string, period: number): boolean {
  return (teamId === meta.home_id) === (period === 1)
}

/** A point in team frame (own goal at x=0) placed on the absolute pitch for the direction the team attacks. */
export function toAbsoluteX(xTeam: number, right: boolean): number {
  return right ? xTeam : 100 - xTeam
}

/** Where a team-frame heat cell sits on the absolute pitch (0-100 units), given the direction the team attacks. */
export function heatCellRect(index: number, right: boolean): { x: number; y: number; w: number; h: number } {
  const col = index % HEAT_COLS
  const row = Math.floor(index / HEAT_COLS)
  const w = 100 / HEAT_COLS
  const h = 100 / HEAT_ROWS
  const xTeam = col * w
  return { x: right ? xTeam : 100 - xTeam - w, y: row * h, w, h }
}

export type HeatCell = { index: number; share: number; level: number } // share of all frames; level against the busiest cell

export function heatCells(grid: number[] | null | undefined): HeatCell[] {
  if (!grid || grid.length !== HEAT_COLS * HEAT_ROWS) return []
  const total = grid.reduce((a, b) => a + b, 0)
  const max = Math.max(...grid)
  if (total <= 0 || max <= 0) return []
  return grid.flatMap((v, index) => (v > 0 ? [{ index, share: v / total, level: v / max }] : []))
}

/** One line a fan can read: the channel and the third where the player has spent most of the match. */
export function heatReading(grid: number[] | null | undefined): string | null {
  if (!grid || grid.length !== HEAT_COLS * HEAT_ROWS) return null
  const total = grid.reduce((a, b) => a + b, 0)
  if (total <= 0) return null
  const sumCols = (lo: number, hi: number) => { let s = 0; for (let r = 0; r < HEAT_ROWS; r++) for (let c = lo; c < hi; c++) s += grid[r * HEAT_COLS + c]; return s }
  const sumRows = (lo: number, hi: number) => { let s = 0; for (let r = lo; r < hi; r++) for (let c = 0; c < HEAT_COLS; c++) s += grid[r * HEAT_COLS + c]; return s }
  const thirds = [sumCols(0, 4), sumCols(4, 8), sumCols(8, 12)]
  const lanes = [sumRows(0, 3), sumRows(3, 5), sumRows(5, 8)]
  const third = ['own third', 'middle third', 'final third'][thirds.indexOf(Math.max(...thirds))]
  const lane = ['left', 'central', 'right'][lanes.indexOf(Math.max(...lanes))]
  return `most of the match in the ${lane} channel of the ${third}`
}

/** Convex hull (Andrew's monotone chain), counter-clockwise, no repeated last point. Fewer than 3 points come back as given. */
export function convexHull(pts: [number, number][]): [number, number][] {
  const p = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1])
  if (p.length < 3) return p
  const cross = (o: [number, number], a: [number, number], b: [number, number]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  const lower: [number, number][] = []
  for (const q of p) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop()
    lower.push(q)
  }
  const upper: [number, number][] = []
  for (let i = p.length - 1; i >= 0; i--) {
    const q = p[i]
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop()
    upper.push(q)
  }
  lower.pop()
  upper.pop()
  return lower.concat(upper)
}

/** Positions between two frames at t in [0, 1]; a player missing from the first frame sits where the second puts them. */
export function lerpFrame(a: Frame | null, b: Frame, t: number): Record<string, [number, number]> {
  const k = Math.max(0, Math.min(1, t))
  const out: Record<string, [number, number]> = {}
  for (const [pid, pb] of Object.entries(b.players)) {
    const pa = a?.players[pid] ?? pb
    out[pid] = [pa[0] + (pb[0] - pa[0]) * k, pa[1] + (pb[1] - pa[1]) * k]
  }
  return out
}

export type BlockPoint = { period: number; minute: number } & Record<string, number>
export type BlockDiff = { period: number; minute: number; diff: number }

/** Home block minus away block per minute (metres), smoothed with a trailing mean so the strip reads calmly. Causal: no look-ahead. */
export function blockDiffSeries(series: BlockPoint[] | null | undefined, meta: Pick<Meta, 'home_id' | 'away_id'>, window = 3): BlockDiff[] {
  const raw = (series ?? [])
    .filter((p) => typeof p[meta.home_id] === 'number' && typeof p[meta.away_id] === 'number')
    .map((p) => ({ period: p.period, minute: p.minute, diff: p[meta.home_id] - p[meta.away_id] }))
  return raw.map((p, i) => {
    const win = raw.slice(Math.max(0, i - window + 1), i + 1)
    return { ...p, diff: win.reduce((s, q) => s + q.diff, 0) / win.length }
  })
}

export type BlockLeader = { text: 'settling' | 'even' | 'pinned back'; side: 'home' | 'away' | null }

/** Who is pinned back: the last smoothed difference, once at least `minPoints` minutes of frames exist. +8 m means the home
 *  block sits higher, so the away side is pinned back; -8 m the reverse. */
export function blockLeader(diff: BlockDiff[] | null | undefined, minPoints = 5): BlockLeader {
  const d = diff ?? []
  if (d.length < minPoints) return { text: 'settling', side: null }
  const last = d[d.length - 1].diff
  if (last >= 8) return { text: 'pinned back', side: 'away' }
  if (last <= -8) return { text: 'pinned back', side: 'home' }
  return { text: 'even', side: null }
}

/** Where a player has been on average: the occupancy-weighted centre of their heat grid, team frame 0-100 (own goal at x=0). */
export function heatCentroid(grid: number[] | null | undefined): [number, number] | null {
  if (!grid || grid.length !== HEAT_COLS * HEAT_ROWS) return null
  let sx = 0, sy = 0, n = 0
  grid.forEach((v, i) => {
    if (v <= 0) return
    const col = i % HEAT_COLS, row = Math.floor(i / HEAT_COLS)
    sx += v * ((col + 0.5) / HEAT_COLS) * 100
    sy += v * ((row + 0.5) / HEAT_ROWS) * 100
    n += v
  })
  return n > 0 ? [sx / n, sy / n] : null
}
