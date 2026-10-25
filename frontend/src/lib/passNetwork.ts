/** A team's pass network from the event stream: who passed to whom, drawn where each player tends to be involved. */

import type { Touch } from './follow'
import { attacksRight, toAbsoluteX } from './tracking'
import type { Meta } from './types'

export type NetNode = { pid: string; x: number; y: number; passes: number } // team frame, attacking right; passes = involvements
export type NetEdge = { from: string; to: string; count: number } // undirected: from < to
export type PassNet = { nodes: NetNode[]; edges: NetEdge[]; passes: number; completed: number }

export const MIN_EDGE = 2
export const MAX_EDGES = 25

/**
 * `positions`, when given, places a node there (team frame) instead of at the mean of its pass coordinates:
 * the positional model's heat centroid spreads players by role, where pass means all drift to the centre circle.
 */
export function passNetwork(touches: Touch[], teamId: string, meta: Pick<Meta, 'home_id'>, half: 1 | 2 | 'all' = 'all',
                            positions?: Record<string, [number, number] | null | undefined>): PassNet {
  const acc = new Map<string, { sx: number; sy: number; n: number }>()
  const pairs = new Map<string, number>()
  let passes = 0, completed = 0
  const add = (pid: string, x: number, y: number) => {
    const a = acc.get(pid) ?? { sx: 0, sy: 0, n: 0 }
    a.sx += x; a.sy += y; a.n += 1
    acc.set(pid, a)
  }
  for (const t of touches) {
    if (t.type !== 'pass' || t.team_id !== teamId || !t.player_id) continue
    if (half !== 'all' && t.period !== half) continue
    if (typeof t.x !== 'number' || typeof t.y !== 'number') continue
    const right = attacksRight(meta, teamId, t.period)
    passes += 1
    add(t.player_id, toAbsoluteX(t.x, right), t.y)
    if (t.outcome === 'complete' && t.receiver_id) {
      completed += 1
      if (typeof t.end_x === 'number' && typeof t.end_y === 'number') add(t.receiver_id, toAbsoluteX(t.end_x, right), t.end_y)
      const key = t.player_id < t.receiver_id ? `${t.player_id}|${t.receiver_id}` : `${t.receiver_id}|${t.player_id}`
      pairs.set(key, (pairs.get(key) ?? 0) + 1)
    }
  }
  const nodes = [...acc.entries()].map(([pid, a]) => {
    const at = positions?.[pid]
    return { pid, x: at ? at[0] : a.sx / a.n, y: at ? at[1] : a.sy / a.n, passes: a.n }
  }).sort((a, b) => a.pid.localeCompare(b.pid))
  const edges = [...pairs.entries()]
    .filter(([, count]) => count >= MIN_EDGE)
    .map(([key, count]) => { const [from, to] = key.split('|'); return { from, to, count } })
    .sort((a, b) => b.count - a.count || a.from.localeCompare(b.from))
    .slice(0, MAX_EDGES)
  return { nodes, edges, passes, completed }
}
