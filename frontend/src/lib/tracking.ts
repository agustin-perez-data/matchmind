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
